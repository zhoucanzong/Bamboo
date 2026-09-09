'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="bamboo-token"]').content;
const SVG = 'http://www.w3.org/2000/svg';
let state = null, selection = null, queue = Promise.resolve(), scale = 1.15, dragging = false, composing = false;
let pending = 0, modalResolve = null, spreadView = false;
const cp = text => Array.from(text);

function feedback(text, error=false) { $('feedback').textContent=text; $('feedback').classList.toggle('error',error); }
async function api(path, data) {
  const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'X-Bamboo-Token':token,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  if(!response.ok){const value=await response.json();throw new Error(value.error||'操作失败');}
  return response;
}
async function json(path,data){return (await api(path,data)).json();}
function pos(block_id,offset){return {block_id,offset};}
function equal(a,b){return a&&b&&a.block_id===b.block_id&&a.offset===b.offset;}
function pointOrder(p){return [state.block_ids.indexOf(p.block_id),p.offset];}
function compare(a,b){const x=pointOrder(a),y=pointOrder(b);return x[0]-y[0]||x[1]-y[1];}
function ordered(){return compare(selection.anchor,selection.focus)<=0?[selection.anchor,selection.focus]:[selection.focus,selection.anchor];}
function selectedText(){
  if(!state||!selection)return '';
  const [a,b]=ordered(),ai=state.block_ids.indexOf(a.block_id),bi=state.block_ids.indexOf(b.block_id);
  return state.book.blocks.slice(ai,bi+1).map((block,i)=>cp(block.inlines.map(s=>s.text).join('')).slice(i===0?a.offset:0,i===bi-ai?b.offset:undefined).join('')).join('\n');
}
function svg(tag,attrs={}){const n=document.createElementNS(SVG,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n;}
function glyphLength(g){const block=state.book.blocks[g.block];const text=block.inlines[g.inline].text;const chars=cp(text);let n=1;while(g.offset+n<chars.length&&/[\u0300-\u036f\ufe00-\ufe0f]/u.test(chars[g.offset+n]))n++;return n;}
function sourceGlyphs(){return state.view.pages.flatMap((p,page)=>p.glyphs.filter(g=>g.block_id).map(g=>({...g,page,end:g.end??g.start+glyphLength(g)})));}
function activeSection(){const i=state.block_ids.indexOf(selection.focus.block_id);return state.view.sections.find(s=>s.block_start<=i&&i<s.block_end)?.spec||{profile:state.book.profile};}
function activeProfile(){return activeSection().profile;}
function pageProfile(index){return state.view.pages[index]?.profile||state.book.profile;}
function caretFor(p){
  const items=sourceGlyphs().filter(g=>g.block_id===p.block_id);
  let g=items.find(g=>g.start===p.offset),after=false;
  if(!g&&items.length){g=items.reduce((a,b)=>Math.abs(a.end-p.offset)<=Math.abs(b.end-p.offset)?a:b);after=true;}
  if(!g){const i=state.block_ids.indexOf(p.block_id);g=state.view.block_starts.find(s=>s.block===i);if(!g)return null;}
  const vertical=pageProfile(g.page).writing_mode==='vertical-rl';
  let x=g.x,y=g.y;if(after){if(vertical)y+=g.height;else x+=g.width;}
  return vertical?{page:g.page,x1:x+g.width*.15,y1:y,x2:x+g.width*.85,y2:y}:{page:g.page,x1:x,y1:y+g.height*.15,x2:x,y2:y+g.height*.85};
}
function localHit(page,x,y){
  const vertical=pageProfile(page).writing_mode==='vertical-rl',items=[];
  for(const g of sourceGlyphs().filter(g=>g.page===page)){
    const dx=Math.max(g.x-x,0,x-g.x-g.width),dy=Math.max(g.y-y,0,y-g.y-g.height),after=vertical?y>g.y+g.height/2:x>g.x+g.width/2;
    items.push({distance:dx*dx+dy*dy,p:pos(g.block_id,after?g.end:g.start)});
  }
  for(const s of state.view.block_starts){if(s.page===page&&!state.book.blocks[s.block].inlines.length)items.push({distance:(x-s.x-s.width/2)**2+(y-s.y-s.height/2)**2,p:pos(state.block_ids[s.block],0)});}
  return items.sort((a,b)=>a.distance-b.distance)[0]?.p||selection.focus;
}
function paintSelection(){
  if(!state||!selection)return;
  if(state.book.special){$('input').blur();$('selection-info').textContent='点击纸面记录或专用工具按钮，可打开记录编辑器。';return;}
  document.querySelectorAll('.selection-layer').forEach(n=>n.replaceChildren());
  const collapsed=equal(selection.anchor,selection.focus),[a,b]=ordered();
  if(!collapsed){for(const g of sourceGlyphs()){
    if(compare(pos(g.block_id,g.end),a)>0&&compare(pos(g.block_id,g.start),b)<0){const layer=document.querySelector(`[data-page="${g.page}"] .selection-layer`);layer?.append(svg('rect',{x:g.x,y:g.y,width:g.width,height:g.height,class:'selection'}));}
  }}
  const caret=caretFor(selection.focus);
  if(caret&&collapsed){const layer=document.querySelector(`[data-page="${caret.page}"] .selection-layer`);layer?.append(svg('line',{...caret,class:'caret'}));}
  const i=state.block_ids.indexOf(selection.focus.block_id),block=state.book.blocks[i];
  if(block){$('block-kind').value=block.kind;$('indent').value=block.indent;$('text-style').value=block.style||(block.kind==='paragraph'?'body':block.kind);}
  const profile=activeProfile(),vertical=profile.writing_mode==='vertical-rl';
  $('font-size').value=profile.font_size;$('rows').value=profile.rows;$('columns').value=profile.columns;$('punctuation').value=profile.punctuation;
  $('rows-label').firstChild.nodeValue=vertical?'每栏字数':'每行字数';$('columns-label').firstChild.nodeValue=vertical?'每面栏数':'每页行数';
  $('vertical').classList.toggle('active',vertical);$('horizontal').classList.toggle('active',!vertical);
  $('mode-label').textContent=(vertical?'竖排':'横排')+' · 可编辑';
  $('section-name').textContent='当前篇章：'+(activeSection().name||'正文');
  $('preset').value=state.view.section?.profile&&JSON.stringify(state.view.section.profile)===JSON.stringify(profile)?state.view.preset:'custom';
  $('selection-info').textContent=collapsed?'光标已定位。直接输入或回车继续。':`已选择 ${cp(selectedText()).length} 字，可设置夹注或旁注。`;
  positionInput(caret);
}
function positionInput(caret){
  if(!caret)return;const page=document.querySelector(`[data-page="${caret.page}"] svg`);if(!page)return;
  const r=page.getBoundingClientRect();$('input').style.left=(r.left+caret.x1*scale)+'px';$('input').style.top=(r.top+caret.y1*scale)+'px';
}
const documentFonts=new Map();
function useDocumentFont(key){
 const name='BambooDocument-'+key;
 if(!documentFonts.has(key)){const face=new FontFace(name,`url(/assets/font?font=${encodeURIComponent(key)})`);document.fonts.add(face);documentFonts.set(key,face.load().catch(e=>feedback('字体加载失败：'+e.message,true)));}
 $('canvas').style.setProperty('--document-font',name);
}
function render(next){
  state=next;selection=structuredClone(next.selection);
  $('font-choice').replaceChildren(...(state.view.fonts||[['auto','默认字体']]).map(([value,label])=>{const o=document.createElement('option');o.value=value;o.textContent=label;return o;}));
  $('font-choice').value=(state.view.fonts||[]).some(([key])=>key===state.book.font)?state.book.font:'auto';$('install-wenkai').hidden=(state.view.fonts||[]).some(([key])=>key==='wenkai');useDocumentFont(state.book.font||'auto');
  document.body.dataset.revision=String(state.revision);
  const profile=activeProfile(),vertical=profile.writing_mode==='vertical-rl';
  const viewportStyle=getComputedStyle($('viewport'));
  const available=$('viewport').clientWidth-parseFloat(viewportStyle.paddingLeft)-parseFloat(viewportStyle.paddingRight);
  scale=$('zoom').value==='fit'?Math.min(1.2,Math.max(.18,(available-(spreadView?24:0))/((spreadView?2:1)*Math.max(...state.view.pages.map((p,i)=>pageProfile(i).width))))):Number($('zoom').value);
  if(document.activeElement!==$('title'))$('title').value=state.book.title;$('undo').disabled=!state.can_undo;$('redo').disabled=!state.can_redo;
  $('font-size').value=profile.font_size;$('rows').value=profile.rows;$('columns').value=profile.columns;$('punctuation').value=profile.punctuation;
  $('rows-label').firstChild.nodeValue=vertical?'每栏字数':'每行字数';$('columns-label').firstChild.nodeValue=vertical?'每面栏数':'每页行数';
  $('preset').value=state.view.preset||'custom';
  $('vertical').classList.toggle('active',vertical);$('horizontal').classList.toggle('active',!vertical);
  $('mode-label').textContent=(vertical?'竖排':'横排')+' · 可编辑';
  $('page-count').textContent=state.view.pages.length+' 页';
  $('word-count').textContent=state.book.blocks.reduce((n,b)=>n+b.inlines.reduce((n,s)=>n+cp(s.text).length,0),0)+' 字';
  const issues=[...(state.import_warnings||[]),...state.view.issues];$('issues').hidden=!issues.length;$('issues').textContent=issues.join('　');
  const canvas=$('canvas');canvas.replaceChildren();canvas.classList.toggle('spread',spreadView);canvas.style.direction=spreadView&&state.book.profile.writing_mode==='vertical-rl'?'rtl':'ltr';
  $('text-style').replaceChildren(...state.view.styles.map(s=>{const o=document.createElement('option');o.value=s.key;o.textContent=s.name;return o;}));
  state.view.pages.forEach((page,index)=>{
    const profile=pageProfile(index);
    const shell=document.createElement('div');shell.className='page';shell.dataset.page=index;shell.style.width=profile.width*scale+'px';
    const paper=svg('svg',{viewBox:`0 0 ${profile.width} ${profile.height}`,width:profile.width*scale,height:profile.height*scale,'aria-label':`第 ${index+1} 页`});
    paper.append(svg('rect',{width:profile.width,height:profile.height,fill:profile.paper}));
    for(const l of page.lines)paper.append(svg('line',{x1:l.x1,y1:l.y1,x2:l.x2,y2:l.y2,stroke:l.color,'stroke-width':l.width}));
    for(const p of page.polygons)paper.append(svg('polygon',{points:p.points.map(p=>p.join(',')).join(' '),fill:p.color}));
    for(const g of page.glyphs){const t=svg('text',{x:g.baseline_x,y:g.baseline_y,'font-size':g.size,fill:g.color,stroke:g.bold?g.color:'none','stroke-width':g.bold?g.size*.022:0});t.textContent=g.text;if(g.annotation_id?.startsWith('annotation-')){t.dataset.annotation=g.annotation_id.split('-')[1];t.classList.add('annotation-link');}if(g.object_id){t.dataset.object=g.object_id;t.dataset.field=g.field;}if(g.reference_id&&g.block<0){t.dataset.reference=g.reference_id;t.classList.add('reference-link');}paper.append(t);}
    if(!state.book.blocks.some(b=>b.inlines.length)&&index===0){const hint=svg('text',{x:profile.width/2,y:profile.height/2,'text-anchor':'middle',class:'empty-hint'});hint.textContent='点击纸面，开始书写';paper.append(hint);}
    paper.append(svg('g',{class:'selection-layer'}));shell.append(paper);canvas.append(shell);
    paper.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;if(event.target.dataset.annotation!==undefined){event.preventDefault();editAnnotation(Number(event.target.dataset.annotation));return;}if(state.book.special){event.preventDefault();openStructured(state.book.special.kind,event.target.dataset.object,event.target.dataset.field);return;}if(event.target.dataset.reference){event.preventDefault();editNumberedNote(event.target.dataset.reference);return;}event.preventDefault();const r=paper.getBoundingClientRect(),p=localHit(index,(event.clientX-r.left)/scale,(event.clientY-r.top)/scale);
      selection=event.shiftKey?{anchor:selection.anchor,focus:p}:{anchor:p,focus:p};dragging=true;paper.setPointerCapture(event.pointerId);paintSelection();$('input').focus({preventScroll:true});
    });
    paper.addEventListener('pointermove',event=>{if(!dragging)return;const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('.page');const actual=target?Number(target.dataset.page):index;const element=target?.querySelector('svg')||paper,r=element.getBoundingClientRect();selection.focus=localHit(actual,(event.clientX-r.left)/scale,(event.clientY-r.top)/scale);paintSelection();});
    paper.addEventListener('pointerup',()=>{dragging=false;syncSelection();});
  });
  $('annotation-list').replaceChildren();state.book.annotations.forEach((note,index)=>{const item=document.createElement('div'),remove=document.createElement('button'),edit=document.createElement('button');remove.textContent='移除';remove.onclick=()=>command({type:'remove_annotation',index});edit.textContent='编辑';edit.onclick=()=>editAnnotation(index);item.append(remove,edit,document.createTextNode((note.placement==='top'?'眉批：':'旁批：')+note.text));$('annotation-list').append(item);});
  (state.view.numbered_notes||[]).forEach((note,index)=>{const item=document.createElement('div'),edit=document.createElement('button');edit.textContent='编辑';edit.onclick=()=>editNumberedNote(note.target);item.append(edit,document.createTextNode(`编号 ${index+1} · ${note.label||'注文'}：${note.text}`));$('annotation-list').append(item);});
  const special=state.book.special;
  for(const id of ['block-kind','text-style','emphasis','plain','label','note','numbered-note','ruby','footnote','annotation','preset','rows','columns','punctuation','indent','styles','chapter','cover','seal','page-templates','page-templates-side','symbols'])$(id).disabled=!!special;
  if(special){$('word-count').textContent=special.records.length+' 条记录';$('mode-label').textContent=({gift:'册簿',genealogy:'族谱',gongche:'工尺谱'}[special.kind])+' · 可编辑';$('section-name').textContent='专用文档';}
  $('save-status').textContent='已自动保存';paintSelection();refreshLibrary();
}
function syncSelection(){if(!state)return;const current=structuredClone(selection);queue=queue.then(()=>json('/api/select/'+state.document_id,current)).catch(e=>feedback(e.message,true));}
function command(operation){
  const savedSelection=structuredClone(selection),id=state.document_id;
  pending++;$('save-status').textContent='正在重排…';
  queue=queue.then(async()=>{
    if(state.document_id!==id)return;
    // Text events queued during a preceding edit continue from its resulting
    // caret. Explicit mouse/format selections remain attached to that action.
    const chosen=operation.followCaret?state.selection:savedSelection;
    const op={...operation};delete op.followCaret;
    if(!['undo','redo','set_metadata','remove_annotation','update_numbered_note','remove_numbered_note'].includes(op.type))op.selection=chosen;
    try{const next=await json('/api/command/'+id,{revision:state.revision,commands:[op]});render(next);feedback('已自动保存');$('input').focus({preventScroll:true});}
    catch(e){feedback(e.message,true);$('save-status').textContent='这次操作未保存';if(op.text){$('recovery').hidden=false;$('recovery').querySelector('textarea').value+=op.text;}if(e.message.includes('文档已更新'))render(await json('/api/document/'+id));}
  }).finally(()=>{pending--;});return queue;
}
function insertText(text){if(state.book.special)return;if(text)command({type:'insert_text',text,followCaret:pending>0});}
function flushInput(){if(composing)return;const value=$('input').value;if(value){$('input').value='';insertText(value);}}
$('input').addEventListener('compositionstart',()=>{composing=true;});
$('input').addEventListener('compositionend',()=>{composing=false;queueMicrotask(flushInput);});
$('input').addEventListener('input',flushInput);
$('input').addEventListener('paste',event=>{event.preventDefault();insertText(event.clipboardData.getData('text/plain'));});
$('input').addEventListener('keydown',event=>{
  if(composing||event.isComposing)return;
  const mod=event.metaKey||event.ctrlKey,key=event.key;
  if(mod&&key.toLowerCase()==='z'){event.preventDefault();command({type:event.shiftKey?'redo':'undo'});return;}
  if(mod&&key.toLowerCase()==='a'){event.preventDefault();const blocks=state.book.blocks,ids=state.block_ids;let last=blocks.length-1;while(blocks[last].kind==='pagebreak')last--;selection={anchor:pos(ids[0],0),focus:pos(ids[last],cp(blocks[last].inlines.map(s=>s.text).join('')).length)};paintSelection();syncSelection();return;}
  if(mod&&['c','x'].includes(key.toLowerCase())){event.preventDefault();const text=selectedText();if(text)navigator.clipboard.writeText(text).then(()=>{if(key.toLowerCase()==='x')command({type:'replace_range',text:''});}).catch(e=>feedback('无法访问剪贴板：'+e.message,true));return;}
  if(key==='Backspace'||key==='Delete'){event.preventDefault();command({type:key==='Backspace'?'delete_backward':'delete_forward',followCaret:pending>0});return;}
  if(key==='Enter'){event.preventDefault();if(event.shiftKey)command({type:'insert_linebreak',followCaret:pending>0});else command({type:'split_paragraph',followCaret:pending>0});return;}
  if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(key)){
    event.preventDefault();if(pending)return;
    let p=selection.focus,vertical=activeProfile().writing_mode==='vertical-rl',i=state.block_ids.indexOf(p.block_id),text=cp(state.book.blocks[i].inlines.map(s=>s.text).join(''));
    const logical=vertical?['ArrowUp','ArrowDown']:['ArrowLeft','ArrowRight'];
    if(key==='Home')p=pos(p.block_id,0);else if(key==='End')p=pos(p.block_id,text.length);
    else if(logical.includes(key)){
      const delta=key===logical[0]?-1:1,boundaries=state.view.boundaries[p.block_id];
      let offset=delta<0?(boundaries.filter(o=>o<p.offset).pop()??-1):(boundaries.find(o=>o>p.offset)??text.length+1);
      if(offset<0&&i>0){i--;while(i>=0&&state.book.blocks[i].kind==='pagebreak')i--;if(i>=0)p=pos(state.block_ids[i],cp(state.book.blocks[i].inlines.map(s=>s.text).join('')).length);}
      else if(offset>text.length&&i<state.block_ids.length-1){i++;while(i<state.block_ids.length&&state.book.blocks[i].kind==='pagebreak')i++;if(i<state.block_ids.length)p=pos(state.block_ids[i],0);}
      else p=pos(p.block_id,Math.max(0,Math.min(text.length,offset)));
    }else{const c=caretFor(p);if(c){const profile=activeProfile();const cross=vertical?(profile.width-2*profile.margin_x-profile.spine)/profile.panels/profile.columns:(profile.height-profile.margin_top-profile.margin_bottom)/profile.columns;p=localHit(c.page,(c.x1+c.x2)/2+(vertical?(key==='ArrowLeft'?-cross:cross):0),(c.y1+c.y2)/2+(!vertical?(key==='ArrowUp'?-cross:cross):0));}}
    selection=event.shiftKey?{anchor:selection.anchor,focus:p}:{anchor:p,focus:p};paintSelection();syncSelection();
  }
});
$('viewport').addEventListener('scroll',()=>{if(state&&selection)positionInput(caretFor(selection.focus));});

async function refreshLibrary(){const value=await json('/api/documents');$('documents').replaceChildren();for(const doc of value.documents){const button=document.createElement('button');button.className='document-item'+(state?.document_id===doc.id?' active':'');button.textContent=doc.title;button.onclick=async()=>{await queue;render(await json('/api/document/'+doc.id));};$('documents').append(button);}}
async function download(response,filename){const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function modal(title,description,fields){
  $('modal-heading').textContent=title;$('modal-description').textContent=description;$('modal-fields').replaceChildren();
  for(const field of fields){
    const label=document.createElement('label');label.textContent=field.label;
    const input=document.createElement(field.options?'select':field.multiline?'textarea':'input');
    input.name=field.name;input.id='modal-'+field.name;label.htmlFor=input.id;
    if(field.options)for(const [value,name]of field.options){const o=document.createElement('option');o.value=value;o.textContent=name;input.append(o);}
    if(field.checkbox){input.type='checkbox';input.checked=!!field.value;label.className='check-row';label.prepend(input);$('modal-fields').append(label);}
    else{if(input.tagName==='INPUT'){input.type=field.type||'text';if(input.type==='number')input.step='any';}input.value=field.value??'';input.required=field.required!==false;$('modal-fields').append(label,input);}
  }
  $('modal').showModal();return new Promise(resolve=>{modalResolve=resolve;});
}
$('modal-form').onsubmit=event=>{event.preventDefault();const values={};for(const e of event.target.elements){if(e.name)values[e.name]=e.type==='checkbox'?e.checked:e.value;}$('modal').close();modalResolve?.(values);modalResolve=null;};
$('cancel').onclick=()=>{$('modal').close();modalResolve?.(null);modalResolve=null;};$('modal').addEventListener('cancel',()=>{modalResolve?.(null);modalResolve=null;});
$('new').onclick=async()=>{await queue;render(await json('/api/documents',{}));$('input').focus();};
$('open').onclick=()=>$('file').click();
$('file').onchange=async()=>{const file=$('file').files[0];if(!file)return;try{await queue;feedback('正在打开…');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));render(await json('/api/import',{filename:file.name,data:btoa(binary)}));feedback('文档已打开');}catch(e){feedback(e.message,true);}$('file').value='';};
$('save').onclick=async()=>{try{await queue;await download(await api('/api/save/'+state.document_id,{}),state.book.title+'.json');feedback('编辑文档副本已保存');}catch(e){feedback(e.message,true);}};
$('export').onclick=async()=>{const answer=await modal('导出文档','导出当前编辑的文档。Word 保留原生文字与横竖方向。',[{name:'format',label:'格式',value:'docx',options:[['docx','Word 文档（可编辑）'],['pdf','PDF'],['html','HTML 阅读文件']]}]);if(!answer)return;try{await queue;feedback('正在导出…');await download(await api('/api/export/'+state.document_id,{format:answer.format}),state.book.title+'.'+answer.format);feedback('已导出');}catch(e){feedback(e.message,true);}};
$('undo').onclick=()=>command({type:'undo'});$('redo').onclick=()=>command({type:'redo'});
$('title').onchange=()=>command({type:'set_metadata',values:{title:$('title').value.trim()||'未命名文档'}});
$('block-kind').onchange=()=>command({type:'set_block',values:{kind:$('block-kind').value,style:''}});
$('emphasis').onclick=()=>command({type:'format_range',kind:'emphasis'});$('plain').onclick=()=>command({type:'format_range',kind:'text'});
$('note').onclick=async()=>{if(!equal(selection.anchor,selection.focus)){command({type:'format_range',kind:'note'});return;}const answer=await modal('插入双行夹注','注释作为两列小字随正文排入。',[{name:'text',label:'夹注文字',multiline:true}]);if(answer)command({type:'insert_inline',kind:'note',text:answer.text});};
$('footnote').onclick=async()=>{const answer=await modal('插入脚注','Word 导出使用原生页下注；页面预览当前以随文小注显示。',[{name:'text',label:'脚注文字',multiline:true}]);if(answer)command({type:'insert_inline',kind:'footnote',text:answer.text});};
$('ruby').onclick=async()=>{if(equal(selection.anchor,selection.focus)){feedback('请先选中要加旁注的正文。',true);return;}const answer=await modal('添加短旁注','旁注与选中的正文一同流动。',[{name:'annotation',label:'旁注文字'}]);if(answer)command({type:'format_range',kind:'ruby',annotation:answer.annotation});};
$('annotation').onclick=()=>editAnnotation();
$('font-choice').onchange=()=>command({type:'set_font',font:$('font-choice').value});
$('label').onclick=async()=>{const a=await modal('注家标签','标签文字与边框可分别编辑。',[{name:'text',label:'标签文字',value:selectedText()||'集解'},{name:'boxed',label:'标签加框',checkbox:true,value:true}]);if(a)command({type:'insert_inline',kind:'label',text:a.text,boxed:a.boxed});};
$('numbered-note').onclick=async()=>{const a=await modal('添加编号注释','在所选文字之后插入引用。编号随注释的插入、删除自动更新。',[{name:'annotation',label:'注家标签（可选）',value:'集解',required:false},{name:'text',label:'注文',multiline:true},{name:'boxed',label:'标签加框',checkbox:true,value:true}]);if(a)command({type:'add_numbered_note',annotation:a.annotation,text:a.text,boxed:a.boxed});};
async function editNumberedNote(target){const note=(state.view.numbered_notes||[]).find(n=>n.target===target);if(!note)return;const a=await modal('编辑编号注释','正文引用与这条注文是关联对象。',[{name:'annotation',label:'注家标签（可选）',value:note.label,required:false},{name:'text',label:'注文',value:note.text,multiline:true,required:false},{name:'boxed',label:'标签加框',checkbox:true,value:note.boxed},{name:'remove',label:'移除这条注释及引用',checkbox:true,value:false}]);if(a)command(a.remove?{type:'remove_numbered_note',target}:{type:'update_numbered_note',target,text:a.text,annotation:a.annotation,boxed:a.boxed});}
async function appearance(){
  const p=activeProfile();
  const promise=modal('版面元素','各项独立设置，不会替换正文或套用整个模板。魚尾和版心文字需要预留版心区域。',[
    {name:'border',label:'边框',value:p.border,options:[['none','不显示'],['single','单边框'],['double','双边框']]},
    {name:'rules',label:'显示界栏',checkbox:true,value:p.rules},
    {name:'spine',label:'预留版心区域',checkbox:true,value:p.spine>0},
    {name:'spine_width',label:'版心宽度（pt）',type:'number',value:p.spine||32},
    {name:'spine_rules',label:'显示版心边线',checkbox:true,value:p.spine>0&&p.spine_rules},
    {name:'fish_tail',label:'显示鱼尾',checkbox:true,value:p.spine>0&&p.fish_tail},
    {name:'show_title',label:'显示版心书名',checkbox:true,value:p.spine>0&&p.show_title},
    {name:'show_volume',label:'显示卷次',checkbox:true,value:p.spine>0&&p.show_volume},
    {name:'show_page_number',label:'显示页码',checkbox:true,value:p.spine>0&&p.show_page_number},
    {name:'show_author',label:'显示版心作者',checkbox:true,value:p.show_author},
    {name:'border_color',label:'边框颜色',type:'color',value:p.border_color||p.rule_color},
    {name:'line_color',label:'界栏颜色',type:'color',value:p.line_color||p.rule_color},
    {name:'fish_tail_color',label:'鱼尾颜色',type:'color',value:p.fish_tail_color||p.rule_color},
    {name:'spine_ink',label:'版心文字颜色',type:'color',value:p.spine_ink||p.ink},
    {name:'ink',label:'正文颜色',type:'color',value:p.ink},
    {name:'accent',label:'强调与印章颜色',type:'color',value:p.accent},
    {name:'punctuation_color',label:'句读颜色',type:'color',value:p.punctuation_color||p.ink},
    {name:'paper',label:'纸张颜色',type:'color',value:p.paper}]);
  const dependents=['spine_rules','fish_tail','show_title','show_volume','show_page_number','show_author'];
  for(const id of dependents)$('modal-'+id).onchange=e=>{if(e.target.checked)$('modal-spine').checked=true;};
  $('modal-spine').onchange=e=>{if(!e.target.checked)for(const id of dependents)$('modal-'+id).checked=false;};
  const clear=document.createElement('button');clear.type='button';clear.textContent='全部关闭';clear.className='element-button';clear.onclick=()=>{$('modal-border').value='none';$('modal-rules').checked=false;$('modal-spine').checked=false;for(const id of dependents)$('modal-'+id).checked=false;$('modal-paper').value='#ffffff';};$('modal-fields').append(clear);
  const a=await promise;if(!a)return;
  command({type:'set_profile',values:{border:a.border,rules:a.rules,spine:a.spine?Number(a.spine_width):0,spine_rules:a.spine_rules,fish_tail:a.fish_tail,show_title:a.show_title,show_volume:a.show_volume,show_page_number:a.show_page_number,paper:a.paper,punctuation_color:a.punctuation_color,ink:a.ink,accent:a.accent,show_author:a.show_author,border_color:a.border_color,line_color:a.line_color,fish_tail_color:a.fish_tail_color,spine_ink:a.spine_ink}});
}
$('appearance').onclick=appearance;$('appearance-side').onclick=appearance;
$('symbols').onclick=async()=>{
  const catalog=await json('/api/symbols'),p=activeProfile();
  const promise=modal('鱼尾符号库','矢量符号不依赖私用区字体。选择样式后可决定是否显示。',[
    {name:'style',label:'样式',value:p.fish_tail_style||'solid',options:catalog.symbols.map(s=>[s.id,s.label])},
    {name:'direction',label:'方向',value:p.fish_tail_direction||'auto',options:[['auto','上下对应'],['down','向下'],['up','向上'],['left','向左'],['right','向右']]},
    {name:'enabled',label:'显示鱼尾',checkbox:true,value:p.fish_tail&&p.spine>0}]);
  const gallery=document.createElement('div');gallery.className='symbol-gallery';
  for(const item of catalog.symbols){const button=document.createElement('button');button.type='button';button.title=item.label;const icon=svg('svg',{viewBox:'0 0 40 40',width:40,height:40});for(const l of item.lines)icon.append(svg('line',{x1:l.x1,y1:l.y1,x2:l.x2,y2:l.y2,stroke:l.color,'stroke-width':l.width}));for(const p of item.polygons)icon.append(svg('polygon',{points:p.points.map(p=>p.join(',')).join(' '),fill:p.color}));button.append(icon,document.createTextNode(item.label));button.onclick=()=>{$('modal-style').value=item.id;};gallery.append(button);}$('modal-fields').prepend(gallery);
  const a=await promise;if(a)command({type:'set_profile',values:{fish_tail_style:a.style,fish_tail_direction:a.direction,fish_tail:a.enabled,spine:a.enabled?(p.spine||32):p.spine}});
};
$('preset').onchange=()=>command({type:'set_profile',preset:$('preset').value});
$('vertical').onclick=()=>{if(activeProfile().writing_mode!=='vertical-rl')command({type:'set_direction',writing_mode:'vertical-rl'});};
$('horizontal').onclick=()=>{if(activeProfile().writing_mode!=='horizontal-tb')command({type:'set_direction',writing_mode:'horizontal-tb'});};
for(const [id,key]of [['font-size','font_size'],['rows','rows'],['columns','columns'],['punctuation','punctuation']])$(id).onchange=()=>command({type:'set_profile',values:{[key]:id==='punctuation'?$(id).value:Number($(id).value)}});
$('indent').onchange=()=>command({type:'set_block',values:{indent:Number($('indent').value)}});
$('zoom').onchange=()=>{const current=structuredClone(selection);render(state);selection=current;paintSelection();};
window.addEventListener('resize',()=>{if(state&&$('zoom').value==='fit'){const current=structuredClone(selection);render(state);selection=current;paintSelection();}});
document.querySelectorAll('.toolbar button').forEach(button=>button.addEventListener('pointerdown',event=>event.preventDefault()));
(async()=>{try{const list=await json('/api/documents');render(list.documents.length?await json('/api/document/'+list.documents[0].id):await json('/api/documents',{}));await document.fonts.ready;feedback('直接点击纸面开始编辑');}catch(e){feedback(e.message,true);}})();

$('text-style').onchange=()=>command({type:'apply_style',style:$('text-style').value});
$('styles').onclick=async()=>{
  const key=$('text-style').value,s=state.view.styles.find(s=>s.key===key);
  const a=await modal('编辑文字样式','修改后，所有使用该样式的段落一起更新。字号比例相对于所在篇章的正文字号。',[
    {name:'name',label:'样式名称',value:s.name},
    {name:'font_scale',label:'字号比例（0.35～3）',type:'number',value:s.font_scale},
    {name:'ink',label:'文字颜色（留空继承）',value:s.ink,required:false},
    {name:'bold',label:'加粗',checkbox:true,value:s.bold},
    {name:'align',label:'对齐',value:s.align,options:[['start','行首 / 栏首'],['center','居中'],['end','行末 / 栏末']]},
    {name:'before',label:'段前空行 / 空栏',type:'number',value:s.before},
    {name:'after',label:'段后空行 / 空栏',type:'number',value:s.after},
    {name:'copy',label:'另存为新样式',checkbox:true,value:false}]);
  if(a){const key=a.copy?'custom-'+Date.now().toString(36):s.key;await command({type:'define_style',values:{key,name:a.name,font_scale:Number(a.font_scale),ink:a.ink,bold:a.bold,align:a.align,before:Number(a.before),after:Number(a.after),role:s.role}});await command({type:'apply_style',style:key});}
};
$('chapter').onclick=async()=>{
 const s=activeSection(),a=await modal('篇章版式','从当前段落另起一篇，或修改当前篇章；每篇独立分页，版心信息和纸面元素可分别设置。',[
 {name:'new',label:'从当前段落开始新篇章',checkbox:true,value:false},
 {name:'name',label:'篇章名称',value:s.name||'正文'},
 {name:'preset',label:'版面样式',value:'',options:[['','保留当前设置'],...state.view.page_styles]},
 {name:'title',label:'版心书名',value:s.title??state.book.title,required:false},
 {name:'volume',label:'卷次 / 篇名',value:s.volume??'',required:false},
 {name:'author',label:'作者 / 译者',value:s.author??'',required:false},
 {name:'page_number_start',label:'起始页码（留空接续）',type:'number',value:s.page_number_start??'',required:false},
 {name:'remove',label:'移除当前分篇，接续上一篇',checkbox:true,value:false}]);
 if(a){if(a.remove)await command({type:'clear_section'});else await command({type:'set_section',new:a.new,preset:a.preset,values:{name:a.name,title:a.title,volume:a.volume,author:a.author,page_number_start:a.page_number_start===''?null:Number(a.page_number_start)}});}
};
$('cover').onclick=async()=>{
 const s=activeSection(),existing=s.page_type==='title-slip';
 const a=await modal(existing?'设置题签封面':'添加题签封面',existing?'书名和卷次可直接点击纸面编辑。':'在文档前添加独立封面，书名和卷次仍可直接编辑。',[
 ...(!existing?[{name:'title',label:'书名',value:state.book.title},{name:'subtitle',label:'卷次',value:'一卷',required:false}]:[]),
 {name:'border',label:'题签边框',value:s.cover_border||'double',options:[['none','无边框'],['single','单线'],['double','双线']]},
 {name:'width',label:'题签宽度（pt）',type:'number',value:s.cover_width||70}]);
 if(a)await command(existing?{type:'set_section',values:{cover_border:a.border,cover_width:Number(a.width)}}:{type:'insert_cover',title:a.title,subtitle:a.subtitle,border:a.border,width:Number(a.width)});
};
$('seal').onclick=async()=>{const a=await modal('文字印章','用可编辑文字排成方印，按竖排自右向左排列。可用于署名落款，最多 16 字。',[
 {name:'text',label:'印文',value:selectedText()||'简牍書屋'},
 {name:'seal_style',label:'印章样式',value:'red',options:[['red','朱文（红字）'],['white','白文（白字红底）']]}]);if(a)await command({type:'insert_inline',kind:'seal',text:a.text,seal_style:a.seal_style});};
$('page-setup').onclick=async()=>{const p=activeProfile(),a=await modal('纸张与留白','设置当前篇章的纸张大小和页边距。单位为 pt，72 pt 约等于 2.54 cm。',[
{name:'width',label:'纸张宽度',type:'number',value:p.width},
{name:'height',label:'纸张高度',type:'number',value:p.height},
{name:'margin_x',label:'左右留白',type:'number',value:p.margin_x},
{name:'margin_top',label:'上方留白',type:'number',value:p.margin_top},
{name:'margin_bottom',label:'下方留白',type:'number',value:p.margin_bottom}]);if(a)await command({type:'set_profile',values:Object.fromEntries(Object.entries(a).map(([k,v])=>[k,Number(v)]))});};

let pageStyleCatalog=null,chosenPageStyle=null;
function paintPageStyleCards(){
 const grid=$('page-style-grid'),category=$('page-style-category').value;
 grid.replaceChildren();
 const items=pageStyleCatalog.filter(s=>category==='all'||s.category===category);
 $('page-style-count').textContent=`${items.length} / ${pageStyleCatalog.length} 种样式`;
 for(const item of items){
  const p=item.profile,card=document.createElement('button');card.type='button';card.className='page-style-card';card.dataset.style=item.id;card.setAttribute('aria-pressed',String(chosenPageStyle===item.id));
  const picture=svg('svg',{viewBox:`0 0 ${p.width} ${p.height}`,'aria-hidden':'true'});
  picture.append(svg('rect',{width:p.width,height:p.height,fill:p.paper}));
  for(const l of item.preview.lines)picture.append(svg('line',{x1:l.x1,y1:l.y1,x2:l.x2,y2:l.y2,stroke:l.color,'stroke-width':l.width}));
  for(const q of item.preview.polygons)picture.append(svg('polygon',{points:q.points.map(p=>p.join(',')).join(' '),fill:q.color}));
  for(const g of item.preview.glyphs){const t=svg('text',{x:g.baseline_x,y:g.baseline_y,'font-size':g.size,fill:g.color});t.textContent=g.text;picture.append(t);}
  const thumb=document.createElement('div');thumb.className='page-style-thumb';thumb.append(picture);
  const title=document.createElement('strong');title.textContent=item.name;
  const detail=document.createElement('span');detail.textContent=`${p.writing_mode==='vertical-rl'?'竖排':'横排'} · ${p.panels===2?(p.writing_mode==='vertical-rl'?'双面':'双栏'):'单页'} · ${p.font_size} 磅`;
  card.append(thumb,title,detail);
  card.onclick=()=>{chosenPageStyle=item.id;grid.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.style===item.id)));$('page-style-description').textContent=item.name+'：'+item.description;$('page-style-apply').disabled=false;};
  grid.append(card);
 }
}
async function openPageStyles(){
 try{
  await queue;
  if(activeSection().page_type==='title-slip'){feedback('请先点击正文篇章，再选择页面样式；封面可通过“题签封面”调整。');return;}
  if(!pageStyleCatalog)pageStyleCatalog=(await json('/api/page-styles')).styles;
  chosenPageStyle=null;$('page-style-new').checked=false;$('page-style-apply').disabled=true;$('page-style-apply').textContent='应用到当前篇章';$('page-style-description').textContent='选择样式查看说明。';
  $('page-style-category').replaceChildren();
  for(const value of ['all',...new Set(pageStyleCatalog.map(s=>s.category))]){const option=document.createElement('option');option.value=value;option.textContent=value==='all'?'全部样式':value;$('page-style-category').append(option);}
  paintPageStyleCards();$('page-style-dialog').showModal();
 }catch(e){feedback(e.message,true);}
}
$('page-templates').onclick=openPageStyles;$('page-templates-side').onclick=openPageStyles;
$('page-style-category').onchange=paintPageStyleCards;
$('page-style-new').onchange=()=>{$('page-style-apply').textContent=$('page-style-new').checked?'从当前段落应用':'应用到当前篇章';};
for(const id of ['page-style-close','page-style-cancel'])$(id).onclick=()=>$('page-style-dialog').close();
$('page-style-apply').onclick=async()=>{if(!chosenPageStyle)return;const preset=chosenPageStyle,start=$('page-style-new').checked;$('page-style-dialog').close();await command({type:'set_section',new:start,preset});};

async function editAnnotation(index=null){
 const note=index===null?null:state.book.annotations[index],p=activeProfile();
 const a=await modal(note?'编辑批注':'添加旁批或眉批','批注锚定所选文字。自动续排会避开正文和其他批注，并在必要时续栏或续页。',[
 {name:'placement',label:'位置',value:note?.placement||'side',options:[['side','栏间旁批'],['top','正文上方眉批']]},
 {name:'text',label:'批注文字',value:note?.text||'',multiline:true},
 {name:'flow',label:'自动续排',checkbox:true,value:note?.flow??true},
 {name:'columns',label:'并排小栏数',type:'number',value:note?.columns||1},
 {name:'extent',label:'每小栏最多字数',type:'number',value:note?.extent||100},
 {name:'font_scale',label:'字号比例（相对正文）',type:'number',value:note?.font_scale??.5},
 {name:'color',label:'批注颜色',type:'color',value:note?.color||p.accent}]);
 if(a){const values={text:a.text,placement:a.placement,flow:a.flow,columns:Number(a.columns),extent:Number(a.extent),font_scale:Number(a.font_scale),color:a.color};await command(note?{type:'update_annotation',index,values}:{type:'add_annotation',...values});}
}

$('spread-view').onclick=()=>{spreadView=!spreadView;$('spread-view').setAttribute('aria-pressed',String(spreadView));$('spread-view').textContent=spreadView?'单页预览':'对页预览';const saved=structuredClone(selection);render(state);selection=saved;paintSelection();};

$('install-wenkai').onclick=async()=>{try{await queue;$('install-wenkai').disabled=true;feedback('正在下载霞鹜文楷字体…');await json('/api/fonts',{install:'wenkai'});for(const face of document.fonts)if(face.family==='BambooDocument-wenkai')document.fonts.delete(face);documentFonts.delete('wenkai');await command({type:'set_font',font:'wenkai'});}catch(e){feedback(e.message,true);}finally{$('install-wenkai').disabled=false;}};
