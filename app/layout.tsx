import type { Metadata } from 'next';
import Script from 'next/script';
import './globals.css';
import './themes.css';
export const metadata: Metadata = {title:'Henge — Motion, reimagined.',description:'An open studio for motion transfer and video swaps with MiniMax H3 and ComfyUI.'};
// Errors thrown by browser extension scripts are not the studio's: an inline script at the top of <head> runs before
// any Next.js chunk, so it drops them before the dev overlay's own listeners see them.
const EXTENSION_ERRORS="(()=>{const x=t=>/(chrome|moz|safari-web)-extension:\\/\\//.test(t||'');window.addEventListener('error',e=>{if(x(e.filename)||x(e.error&&e.error.stack)){e.stopImmediatePropagation();e.preventDefault();}},true);window.addEventListener('unhandledrejection',e=>{if(x(e.reason&&e.reason.stack)){e.stopImmediatePropagation();e.preventDefault();}},true);})();";
// The saved theme ('system' follows the OS) before the first paint: no flash of the wrong colors.
const THEME="(()=>{try{let t=localStorage.getItem('henge-theme')||'system';if(t==='system')t=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';document.documentElement.dataset.theme=t;}catch(e){}})();";
export default function Layout({children}:Readonly<{children:React.ReactNode}>) {return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{__html:EXTENSION_ERRORS+THEME}}/></head><body><Script src="/hydration-guard.js" strategy="beforeInteractive"/>{children}</body></html>;}
