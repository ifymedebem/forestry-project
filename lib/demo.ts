import type {Project} from './types';
export const demo:Project = {
 id:'demo',name:'Rio Verde Forest Project',created_at:'2026-11-09T08:30:00Z',status:'complete',stage:'Ready for human review',area_ha:12480,
 boundary:{type:'Polygon',coordinates:[[[-70.49,-9.04],[-70.47,-8.965],[-70.40,-8.92],[-70.32,-8.94],[-70.30,-8.985],[-70.35,-9.035],[-70.42,-9.06],[-70.49,-9.04]]]},
 document:{name:'Rio_Verde_Project_Description.pdf',bytes:2466816,sha256:'Illustrative sample — no original project document'},
 settings:{baseline_start:'2022-06-01',baseline_end:'2022-09-30',monitoring_start:'2024-06-01',monitoring_end:'2024-09-30'},
 result:{run_id:'SAMPLE-001',finished_at:'2026-11-09T08:42:00Z',extraction_method:'Illustrative sample claims',
 claims:[
 {id:'CLM-001',title:'No significant forest disturbance during the monitoring period',quote:'No significant forest disturbance was observed within the project boundary during the 2024 monitoring period.',page:24,category:'disturbance',status:'needs review'},
 {id:'CLM-002',title:'Project boundary covers 12,480 hectares',quote:'The total project area encompasses 12,480 hectares of tropical forest in the state of Acre, Brazil.',page:8,category:'project area',status:'context available'},
 {id:'CLM-003',title:'Forest canopy cover remains above 90%',quote:'Forest canopy cover has remained above 90% across the project area since the baseline assessment.',page:18,category:'forest cover',status:'needs review'},
 {id:'CLM-004',title:'Annual satellite monitoring is in place',quote:'The project uses annual satellite monitoring alongside quarterly field observations to identify land-cover changes.',page:32,category:'monitoring',status:'context available'},
 {id:'CLM-005',title:'No fire events reported in 2024',quote:'No fire-related forest loss was reported within the project boundary in 2024.',page:26,category:'disturbance',status:'requires review'},
 {id:'CLM-006',title:'Baseline forest condition established in 2022',quote:'The 2022 baseline assessment documented a predominantly closed-canopy tropical forest.',page:15,category:'forest cover',status:'context available'},
 {id:'CLM-007',title:'Carbon stock estimates use field inventory data',quote:'Above-ground carbon stock estimates are derived from permanent sample plots and species-specific allometric equations.',page:41,category:'carbon',status:'requires review'},
 {id:'CLM-008',title:'Boundary maintained throughout the crediting period',quote:'The project boundary has remained unchanged throughout the current crediting period.',page:10,category:'project area',status:'context available'}
 ],findings:[
 {id:'FND-001',title:'Possible vegetation disturbance',description:'An illustrative 42.6 ha signal exceeds the NDVI decline threshold in the southeastern part of the sample boundary. Inspect the source imagery and seasonal context before interpreting this signal.',status:'needs review',rule:'ndvi-screen-v1.0.0',claim_ids:['CLM-001','CLM-003']},
 {id:'FND-002',title:'Canopy cover claim needs closer review',description:'An NDVI screening indicator cannot directly establish a 90% canopy cover claim. A calibrated canopy product and aligned reference dates are needed.',status:'needs review',rule:'claim-alignment-v1.0.0',claim_ids:['CLM-003']},
 {id:'FND-003',title:'Fire attribution remains unverified',description:'Vegetation change alone does not establish fire as its cause. Check active-fire records and high-resolution imagery before confirming or dismissing the claim.',status:'requires review',rule:'attribution-v1.0.0',claim_ids:['CLM-005']}
 ],limitations:['This is a fictional sample project. Claims, coverage, findings and highlighted areas are illustrative, not results of satellite analysis.','The map uses an undated Esri satellite mosaic for geographic context; it is not dated before/after evidence.','Vegetation indicators can be affected by seasonality, drought, fire, harvest, clouds and sensor effects.','Satellite screening cannot establish carbon additionality, credit validity or causal attribution.','Registry records have not been imported.'],
 satellite:{valid_coverage:.943,flagged_ha:42.6,interpretation:'Illustrative possible disturbance',rule_version:'ndvi-screen-v1.0.0',baseline_median:.81,monitoring_median:.72,sources:[
 {id:'Sentinel-2 L2A catalogue',period:'reference',datetime:'',url:'https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a'},
 {id:'Sentinel-2 documentation',period:'methodology',datetime:'',url:'https://sentiwiki.copernicus.eu/web/s2-mission'},
 {id:'NDVI screening method',period:'methodology',datetime:'',url:'https://www.usgs.gov/landsat-missions/landsat-normalized-difference-vegetation-index'}
 ],flagged_areas:{type:'FeatureCollection',features:[{type:'Feature',properties:{kind:'Illustrative signal'},geometry:{type:'Polygon',coordinates:[[[-70.355,-9.011],[-70.337,-9.002],[-70.323,-9.012],[-70.343,-9.025],[-70.355,-9.011]]]}},{type:'Feature',properties:{kind:'Illustrative signal'},geometry:{type:'Polygon',coordinates:[[[-70.407,-8.96],[-70.395,-8.953],[-70.383,-8.963],[-70.399,-8.971],[-70.407,-8.96]]]}}]}}
 },reviews:{}
};
