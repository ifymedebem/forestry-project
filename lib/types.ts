export type Claim = {id:string; title:string; quote:string; page:number; category:string; status:string; method?:string};
export type Finding = {id:string; title:string; description:string; status:string; rule:string; claim_ids:string[]};
export type Review = {decision:string; note:string; updated_at?:string};
export type Source = {id:string; period:string; datetime:string; cloud_cover?:number; url:string};
export type Project = {
 id:string; name:string; created_at:string; status:string; stage:string; boundary:GeoJSON.Geometry; area_ha:number;
 document:{name:string;sha256?:string;bytes:number}; settings:Record<string,string>;
 result:{run_id?:string;finished_at?:string;claims:Claim[];findings:Finding[];extraction_method?:string;limitations:string[];satellite?:{valid_coverage:number;flagged_ha:number;valid_ha?:number;baseline_median?:number;monitoring_median?:number;interpretation:string;rule_version:string;sources:Source[];flagged_areas?:GeoJSON.FeatureCollection;bounds?:number[]};provenance?:unknown};
 reviews:Record<string,Review>;
};
