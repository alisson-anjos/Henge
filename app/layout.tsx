import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'OpenJutsu — Motion, reimagined.',description:'An open studio for motion transfer and video swaps with MiniMax H3 guide latents.'};
export default function Layout({children}:Readonly<{children:React.ReactNode}>) {return <html lang="en"><body>{children}</body></html>;}
