"""Bounded Sentinel-2 screening; versioned thresholds are screening rules, not attribution."""
import io
import math
import os
import warnings

import httpx
import numpy as np
from PIL import Image
from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

CATALOG = 'https://earth-search.aws.element84.com/v1'
RULE_VERSION = 'ndvi-screen-v1.0.0'
RULES = {'baseline_ndvi_min': 0.5, 'ndvi_drop_min': 0.2, 'valid_coverage_min': 0.6, 'scene_cloud_max': 30, 'resolution_m': 60, 'max_scenes_per_period': 8, 'min_observations': 2}

def reflectance(raw, asset, properties):
    info = asset.get('raster:bands', [{}])[0]
    # Earth Search COGs can have the BOA additive offset already baked into DN.
    # Do not apply the STAC offset a second time to these harmonized assets.
    offset = 0 if properties.get('earthsearch:boa_offset_applied') is True else info.get('offset', 0)
    return raw * info.get('scale', 0.0001) + offset

def validate_boundary(raw):
    if raw.get('type') == 'FeatureCollection':
        geometries = [shape(f['geometry']) for f in raw.get('features', []) if f.get('geometry')]
        if not geometries:
            raise ValueError('The boundary contains no features.')
        geom = unary_union(geometries)
    else:
        geom = shape(raw['geometry'] if raw.get('type') == 'Feature' else raw)
    if geom.geom_type not in ('Polygon', 'MultiPolygon') or geom.is_empty or not geom.is_valid:
        raise ValueError('Upload valid Polygon or MultiPolygon geometry in WGS84 longitude/latitude.')
    x1, y1, x2, y2 = geom.bounds
    if not (-180 <= x1 < x2 <= 180 and -85 <= y1 < y2 <= 85) or x2 - x1 > 180:
        raise ValueError('Boundary coordinates must be WGS84; dateline crossing is not yet supported.')
    if len(geom.wkt) > 2000000:
        raise ValueError('Simplify the boundary to fewer vertices.')
    area = abs(Geod(ellps='WGS84').geometry_area_perimeter(geom)[0]) / 10000
    if not 0.1 <= area <= 50000:
        raise ValueError('The initial screening supports boundaries from 0.1 to 50,000 hectares.')
    return mapping(geom), round(area, 2)

def catalogue_scenes(boundary, start, end):
    response = httpx.post(CATALOG + '/search', json={'collections': ['sentinel-2-l2a'], 'intersects': boundary, 'datetime': f'{start}T00:00:00Z/{end}T23:59:59Z', 'limit': 100, 'query': {'eo:cloud_cover': {'lte': RULES['scene_cloud_max']}}}, timeout=45)
    response.raise_for_status()
    data = response.json()
    features = data.get('features', [])
    truncated = len(features) >= 100 and any(link.get('rel') == 'next' for link in data.get('links', []))
    # Sample evenly through the period; retain enough granules for AOI mosaics.
    features.sort(key=lambda x: x['properties']['datetime'])
    if len(features) > RULES['max_scenes_per_period']:
        indexes = np.linspace(0, len(features)-1, RULES['max_scenes_per_period'], dtype=int)
        features = [features[int(i)] for i in indexes]
    return features, bool(truncated)

def compare_arrays(baseline, monitoring, inside, pixel_ha, baseline_count=None, monitoring_count=None):
    valid = inside & np.isfinite(baseline) & np.isfinite(monitoring)
    if baseline_count is not None:
        valid &= baseline_count >= RULES['min_observations']
    if monitoring_count is not None:
        valid &= monitoring_count >= RULES['min_observations']
    coverage = float(valid.sum() / max(1, inside.sum()))
    changed = valid & (baseline >= RULES['baseline_ndvi_min']) & ((baseline - monitoring) >= RULES['ndvi_drop_min'])
    return {'valid_coverage': round(coverage, 4), 'flagged_ha': round(float(changed.sum()) * pixel_ha, 2), 'valid_ha': round(float(valid.sum()) * pixel_ha, 2), 'baseline_median': round(float(np.median(baseline[valid])), 3) if valid.any() else None, 'monitoring_median': round(float(np.median(monitoring[valid])), 3) if valid.any() else None, 'flag_mask': changed, 'valid_mask': valid}

def analyze(boundary, settings):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask, shapes
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import transform_bounds, transform_geom
    geom = shape(boundary)
    lon, lat = geom.centroid.x, geom.centroid.y
    crs = f'EPSG:{(32600 if lat >= 0 else 32700) + min(60, max(1, int((lon + 180)/6) + 1))}'
    xmin, ymin, xmax, ymax = transform_bounds('EPSG:4326', crs, *geom.bounds)
    res = RULES['resolution_m']
    width, height = max(1, math.ceil((xmax-xmin)/res)), max(1, math.ceil((ymax-ymin)/res))
    if width * height > 2000000:
        raise ValueError('Boundary extent is too large for this screening grid. Use a compact project boundary.')
    transform = from_origin(xmin, ymax, res, res)
    local_geom = transform_geom('EPSG:4326', crs, boundary)
    inside = geometry_mask([local_geom], (height, width), transform, invert=True)
    if not inside.any():
        raise ValueError('Boundary is smaller than the 60 m screening grid; use a larger boundary.')
    scene_sources, composites, counts, limitations = [], [], [], []
    # GDAL uses inherited proxy and CA configuration. No TLS verification bypass.
    env = {'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR', 'GDAL_HTTP_TIMEOUT': '45', 'GDAL_HTTP_MAX_RETRY': '2', 'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.tif,.tiff'}
    if os.getenv('HTTPS_PROXY'):
        env['GDAL_HTTP_PROXY'] = os.environ['HTTPS_PROXY']
    if os.getenv('CURL_CA_BUNDLE') or os.getenv('SSL_CERT_FILE'):
        env['GDAL_HTTP_CAINFO'] = os.getenv('CURL_CA_BUNDLE') or os.environ['SSL_CERT_FILE']
    for label in ('baseline', 'monitoring'):
        scenes, truncated = catalogue_scenes(boundary, settings[label + '_start'], settings[label + '_end'])
        if truncated:
            limitations.append(f'{label}: catalogue returned more than 100 granules; only the first page was sampled. Review temporal representativeness.')
        stack = []
        for scene in scenes:
            try:
                bands = []
                with rasterio.Env(**env):
                    for key in ('red', 'nir', 'scl'):
                        asset = scene['assets'][key]
                        with rasterio.open(asset['href']) as dataset:
                            with WarpedVRT(dataset, crs=crs, transform=transform, width=width, height=height, resampling=Resampling.nearest if key == 'scl' else Resampling.bilinear) as vrt:
                                band = vrt.read(1, masked=True).astype('float32').filled(np.nan)
                                if key != 'scl':
                                    band = reflectance(band, asset, scene['properties'])
                                bands.append(band)
                red, nir, scl = bands
                valid = inside & np.isin(scl, [4, 5]) & np.isfinite(red) & np.isfinite(nir) & (red >= 0) & (nir >= 0) & ((red+nir) > 0)
                ndvi = np.full((height, width), np.nan, dtype='float32')
                np.divide(nir-red, nir+red, out=ndvi, where=valid)
                ndvi[~valid] = np.nan
                stack.append(ndvi)
                scene_sources.append({'id': scene['id'], 'period': label, 'datetime': scene['properties']['datetime'], 'cloud_cover': scene['properties'].get('eo:cloud_cover'), 'url': f'{CATALOG}/collections/sentinel-2-l2a/items/{scene["id"]}', 'assets': {k: scene['assets'][k]['href'] for k in ('red', 'nir', 'scl')}})
            except Exception as error:
                limitations.append(f'Scene {scene["id"]} unavailable ({type(error).__name__}); excluded from composite.')
        if not stack:
            raise ValueError(f'No readable Sentinel-2 observations for the {label} period. Try a broader date range.')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            composite = np.nanmedian(np.stack(stack), axis=0)
        composites.append(composite)
        counts.append(np.sum(np.isfinite(np.stack(stack)), axis=0))
    result = compare_arrays(*composites, inside, res * res / 10000, *counts)
    flagged = result.pop('flag_mask')
    valid = result.pop('valid_mask')
    features = []
    for geometry, value in shapes(flagged.astype('uint8'), mask=flagged, transform=transform):
        if value:
            features.append({'type': 'Feature', 'properties': {'kind': 'possible disturbance'}, 'geometry': transform_geom(crs, 'EPSG:4326', geometry)})
    images = {}
    for label, values in zip(('baseline', 'monitoring'), composites):
        rgba = np.zeros((height, width, 4), dtype='uint8')
        intensity = np.nan_to_num(np.clip((values + 0.2) / 1.2, 0, 1))
        rgba[..., 0] = (185 * (1-intensity)).astype('uint8')
        rgba[..., 1] = (75 + 100 * intensity).astype('uint8')
        rgba[..., 2] = (52 * (1-intensity) + 45).astype('uint8')
        rgba[..., 3] = np.where(inside & np.isfinite(values), 255, 0)
        output = io.BytesIO()
        Image.fromarray(rgba).save(output, format='PNG')
        images[label] = output.getvalue()
    if result['valid_coverage'] < RULES['valid_coverage_min']:
        limitations.append('Comparable coverage is below 60%; evidence is insufficient for a boundary-wide conclusion.')
    limitations += ['NDVI decline is a screening signal; seasonal variation, drought, fire, harvest, clouds and sensor effects can produce similar signals.', '60 m median composites can miss small or short-lived changes. Cloud masks are imperfect; unobserved pixels are excluded.', 'Satellite observations cannot establish carbon additionality, permanence, ownership, credits or causal attribution.']
    return {**result, 'sources': scene_sources, 'flagged_areas': {'type': 'FeatureCollection', 'features': features}, 'limitations': limitations, 'rule_version': RULE_VERSION, 'rules': RULES, 'grid_crs': crs, 'bounds': list(geom.bounds), 'interpretation': 'insufficient evidence' if result['valid_coverage'] < 0.6 else 'possible disturbance' if result['flagged_ha'] > 0 else 'no threshold exceedance in observed pixels'}, images
