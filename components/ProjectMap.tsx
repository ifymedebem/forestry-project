'use client';
import {useEffect,useRef,useState} from 'react';
import maplibregl from 'maplibre-gl';
import {Expand,Layers,Minus,Plus,LocateFixed} from 'lucide-react';
import type {Project} from '@/lib/types';

export default function ProjectMap({project,onInspect}:{project:Project;onInspect:()=>void}){
 const container=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null);
 const inspectRef=useRef(onInspect);inspectRef.current=onInspect;
 const [layer,setLayer]=useState(true),[loaded,setLoaded]=useState(false),[error,setError]=useState(false),[expanded,setExpanded]=useState(false);
 useEffect(()=>{
  if(!container.current)return;
  let m:maplibregl.Map;
  try{m=new maplibregl.Map({container:container.current,center:[-70.40,-8.99],zoom:11.2,attributionControl:{compact:true},style:{version:8,sources:{satellite:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,attribution:'Tiles © Esri · Maxar · Earthstar Geographics'}},layers:[{id:'satellite',type:'raster',source:'satellite',paint:{'raster-saturation':-.3,'raster-brightness-max':.84}}]}});map.current=m;
  m.on('load',()=>{setLoaded(true);m.addSource('boundary',{type:'geojson',data:{type:'Feature',properties:{},geometry:project.boundary}});m.addLayer({id:'boundary-fill',type:'fill',source:'boundary',paint:{'fill-color':'#d7e8a5','fill-opacity':.08}});m.addLayer({id:'boundary-line',type:'line',source:'boundary',paint:{'line-color':'#e3f0b0','line-width':2.5,'line-dasharray':[4,2]}});m.addSource('flags',{type:'geojson',data:project.result.satellite?.flagged_areas||{type:'FeatureCollection',features:[]}});m.addLayer({id:'flags-fill',type:'fill',source:'flags',paint:{'fill-color':'#f2ad64','fill-opacity':.65}});m.addLayer({id:'flags-line',type:'line',source:'flags',paint:{'line-color':'#ffc685','line-width':2}});m.on('click','flags-fill',()=>inspectRef.current());m.on('mouseenter','flags-fill',()=>{m.getCanvas().style.cursor='pointer'});m.on('mouseleave','flags-fill',()=>{m.getCanvas().style.cursor=''});fit(m,project.boundary)});
  m.on('error',()=>setError(true));
  }catch{setError(true)}
  return()=>{m?.remove();map.current=null;setLoaded(false)};
 },[project.id]);
 useEffect(()=>{const m=map.current;if(m?.getLayer('flags-fill')){m.setLayoutProperty('flags-fill','visibility',layer?'visible':'none');m.setLayoutProperty('flags-line','visibility',layer?'visible':'none')}},[layer,loaded]);
 useEffect(()=>{const source=map.current?.getSource('flags') as maplibregl.GeoJSONSource|undefined;source?.setData(project.result.satellite?.flagged_areas||{type:'FeatureCollection',features:[]})},[project.result.satellite?.flagged_areas,loaded]);
 useEffect(()=>{const timer=setTimeout(()=>map.current?.resize(),50);return()=>clearTimeout(timer)},[expanded]);
 function fit(m:maplibregl.Map,geom:GeoJSON.Geometry){const b=new maplibregl.LngLatBounds();function scan(v:unknown){if(Array.isArray(v)){if(typeof v[0]==='number')b.extend(v as [number,number]);else v.forEach(scan)}}if('coordinates'in geom)scan(geom.coordinates);if(!b.isEmpty())m.fitBounds(b,{padding:55,duration:700})}
 return <div className={`map-shell ${expanded?'expanded':''}`}>
  <div className="map-canvas" ref={container} style={{backgroundImage:"url('/images/forest.jpg')"}}/>
  <div className="map-top"><span className="map-mode"><span className="live-dot"/>Satellite context</span><button className="map-button" aria-label={expanded?'Exit expanded map':'Expand map'} onClick={()=>setExpanded(!expanded)}><Expand size={16}/></button></div>
  {project.id==='demo'&&<button className="map-label" onClick={onInspect}><span/>Possible disturbance <b>↗</b><small>Illustrative signal</small></button>}
  <div className="map-controls"><button className="map-button" aria-label="Zoom in" onClick={()=>map.current?.zoomIn()}><Plus size={17}/></button><button className="map-button" aria-label="Zoom out" onClick={()=>map.current?.zoomOut()}><Minus size={17}/></button><button className="map-button" aria-label="Fit project boundary" onClick={()=>map.current&&fit(map.current,project.boundary)}><LocateFixed size={17}/></button></div>
  <div className="map-legend"><span><i className="boundary-key"/>Project boundary</span><button onClick={()=>setLayer(!layer)} aria-pressed={layer}><i className="flag-key" style={{opacity:layer?1:.3}}/>{project.id==='demo'?'Sample signal':'Screening signal'}</button><button className="layers-button" onClick={()=>setLayer(!layer)} aria-label="Toggle flagged areas"><Layers size={15}/></button></div>
  {error&&!loaded&&<span className="map-error">Interactive map unavailable · context image shown</span>}
  <div className="map-caption">Undated satellite mosaic · geographic context only</div>
 </div>
}
