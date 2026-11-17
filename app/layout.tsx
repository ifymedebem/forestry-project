import type {Metadata} from 'next';
import './globals.css';
import 'maplibre-gl/dist/maplibre-gl.css';
export const metadata:Metadata={title:'Canopy — Forest Carbon Review',description:'Follow the evidence. Review forest carbon claims with source-linked documents, satellite screening and human judgment.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
