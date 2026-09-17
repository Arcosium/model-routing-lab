"""Render the local report with Playwright CLI; keep all browser state in vault."""
import argparse
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import json
import os
from pathlib import Path
import subprocess
import threading
from lab import STATE,dump

p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
p.add_argument('--review-name',default='render-review');p.add_argument('--skip-pdf',action='store_true');a=p.parse_args()
root=a.directory.resolve()
if not root.is_relative_to(STATE):raise ValueError('Artifacts must remain in vault')
qa=root/a.review_name;qa.mkdir(exist_ok=False)
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/favicon.ico':
            self.send_response(204);self.end_headers();return
        super().do_GET()
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
env=os.environ.copy();env['PWTEST_DAEMON_SESSION_DIR']=str(STATE/'browser-daemon')
env['NO_UPDATE_NOTIFIER']='1'
base=['playwright-cli','-s=routing-lab-review']
def call(args,label):
    r=subprocess.run(base+args,cwd=qa,env=env,capture_output=True,text=True,timeout=55)
    (qa/(label+'.log')).write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(f'Playwright {label} failed; inspect private log')
    return r.stdout
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        executable=pw.chromium.executable_path
    config=qa/'browser-config.json'
    dump(config,{'browser':{'browserName':'chromium','launchOptions':{'executablePath':executable,'headless':True}}})
    call(['open','--config='+str(config),'--profile='+str(STATE/'browser-profile')],'open')
    script='''async page => {
      const errors=[];
      page.on('pageerror',e=>errors.push(String(e)));
      page.on('console',m=>{if(m.type()==='error') errors.push(m.text())});
      await page.setViewportSize({width:1440,height:900});
      await page.goto(URL,{waitUntil:'networkidle'});
      await page.evaluate(()=>document.fonts.ready);
      const check=()=>page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,brokenImages:[...document.images].filter(x=>!x.complete||x.naturalWidth===0).length,title:document.title}));
      const desktop=await check();
      await page.screenshot({path:DESKTOP,fullPage:true});
      await page.pdf({path:PDF,printBackground:true,preferCSSPageSize:true});
      await page.setViewportSize({width:390,height:844});
      await page.screenshot({path:MOBILE,fullPage:true});
      const mobile=await check();
      return {desktop,mobile,errors};
    }'''
    if a.skip_pdf:script=script.replace("await page.pdf({path:PDF,printBackground:true,preferCSSPageSize:true});",'')
    for key,value in {'URL':f'http://127.0.0.1:{server.server_port}/report.html','DESKTOP':str(qa/'desktop.png'),'MOBILE':str(qa/'mobile.png'),'PDF':str(root/'report.pdf')}.items():script=script.replace(key,json.dumps(value))
    result=call(['run-code',script],'render')
    print(result)
    call(['console','error'],'console')
finally:
    call(['close'],'close');server.shutdown()
from PIL import Image
for name in ['desktop','mobile']:
    with Image.open(qa/(name+'.png')) as im:
        im.resize((max(1,im.width//4),max(1,im.height//4))).save(qa/(name+'-25pct.png'))
