export type Connection = {url:string;token:string};
export async function api(path:string, connection:Connection, options:RequestInit={}) {
 const headers = new Headers(options.headers);
 if(connection.token) headers.set('Authorization',`Bearer ${connection.token}`);
 const response=await fetch(`${connection.url.replace(/\/$/,'')}/api${path}`,{...options,headers});
 if(!response.ok){let detail;try{detail=(await response.json()).detail}catch{detail=`Request failed (${response.status})`};throw new Error(typeof detail==='string'?detail:JSON.stringify(detail))}
 return response;
}
export function downloadText(content:string,name:string,type='text/html'){
 const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
}
