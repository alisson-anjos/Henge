import type { Metadata } from 'next';
import Script from 'next/script';
import './globals.css';
export const metadata: Metadata = {title:'Kagemane — Motion, reimagined.',description:'An open studio for motion transfer and video swaps with MiniMax H3 guide latents.'};
export default function Layout({children}:Readonly<{children:React.ReactNode}>) {return <html lang="en"><body><Script src="/hydration-guard.js" strategy="beforeInteractive"/>{children}</body></html>;}
