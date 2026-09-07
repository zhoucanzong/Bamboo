'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="bamboo-token"]').content;
const SVG = 'http://www.w3.org/2000/svg';
let state = null, selection = null, queue = Promise.resolve(), scale = 1.15, dragging = false, composing = false;
let pending = 0, modalResolve = null;
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
function caretFor(p){
  const items=sourceGlyphs().filter(g=>g.block_id===p.block_id);
  let g=items.find(g=>g.start===p.offset),after=false;
  if(!g&&items.length){g=items.reduce((a,b)=>Math.abs(a.end-p.offset)<=Math.abs(b.end-p.offset)?a:b);after=true;}
  const vertical=state.book.profile.writing_mode==='vertical-rl';
  if(!g){const i=state.block_ids.indexOf(p.block_id);g=state.view.block_starts.find(s=>s.block===i);if(!g)return null;}
  let x=g.x,y=g.y;if(after){if(vertical)y+=g.height;else x+=g.width;}
  return vertical?{page:g.page,x1:x+g.width*.15,y1:y,x2:x+g.width*.85,y2:y}:{page:g.page,x1:x,y1:y+g.height*.15,x2:x,y2:y+g.height*.85};
}
function localHit(page,x,y){
  const vertical=state.book.profile.writing_mode==='vertical-rl',items=[];
  for(const g of sourceGlyphs().filter(g=>g.page===page)){
    const dx=Math.max(g.x-x,0,x-g.x-g.width),dy=Math.max(g.y-y,0,y-g.y-g.height),after=vertical?y>g.y+g.height/2:x>g.x+g.width/2;
    items.push({distance:dx*dx+dy*dy,p:pos(g.block_id,after?g.end:g.start)});
  }
  for(const s of state.view.block_starts){if(s.page===page&&!state.book.blocks[s.block].inlines.length)items.push({distance:(x-s.x-s.width/2)**2+(y-s.y-s.height/2)**2,p:pos(state.block_ids[s.block],0)});}
  return items.sort((a,b)=>a.distance-b.distance)[0]?.p||selection.focus;
}
function paintSelection(){
  if(!state||!selection)return;
  document.querySelectorAll('.selection-layer').forEach(n=>n.replaceChildren());
  const collapsed=equal(selection.anchor,selection.focus),[a,b]=ordered();
  if(!collapsed){for(const g of sourceGlyphs()){
    if(compare(pos(g.block_id,g.end),a)>0&&compare(pos(g.block_id,g.start),b)<0){const layer=document.querySelector(`[data-page="${g.page}"] .selection-layer`);layer?.append(svg('rect',{x:g.x,y:g.y,width:g.width,height:g.height,class:'selection'}));}
  }}
  const caret=caretFor(selection.focus);
  if(caret&&collapsed){const layer=document.querySelector(`[data-page="${caret.page}"] .selection-layer`);layer?.append(svg('line',{...caret,class:'caret'}));}
  const i=state.block_ids.indexOf(selection.focus.block_id),block=state.book.blocks[i];
  if(block){$('block-kind').value=block.kind;$('indent').value=block.indent;}
  $('selection-info').textContent=collapsed?'光标已定位。直接输入或回车继续。':`已选择 ${cp(selectedText()).length} 字，可设置夹注或旁注。`;
  positionInput(caret);
}
function positionInput(caret){
  if(!caret)return;const page=document.querySelector(`[data-page="${caret.page}"] svg`);if(!page)return;
  const r=page.getBoundingClientRect();$('input').style.left=(r.left+caret.x1*scale)+'px';$('input').style.top=(r.top+caret.y1*scale)+'px';
}
function render(next){
  state=next;selection=structuredClone(next.selection);
  document.body.dataset.revision=String(state.revision);
  const profile=state.book.profile,vertical=profile.writing_mode==='vertical-rl';
  const viewportStyle=getComputedStyle($('viewport'));
  const available=$('viewport').clientWidth-parseFloat(viewportStyle.paddingLeft)-parseFloat(viewportStyle.paddingRight);
  scale=$('zoom').value==='fit'?Math.min(1.2,Math.max(.35,available/profile.width)):Number($('zoom').value);
  if(document.activeElement!==$('title'))$('title').value=state.book.title;$('undo').disabled=!state.can_undo;$('redo').disabled=!state.can_redo;
  $('font-size').value=profile.font_size;$('rows').value=profile.rows;$('columns').value=profile.columns;$('punctuation').value=profile.punctuation;
  $('rows-label').firstChild.nodeValue=vertical?'每栏字数':'每行字数';$('columns-label').firstChild.nodeValue=vertical?'每面栏数':'每页行数';
  $('preset').value=state.view.preset||'custom';
  $('vertical').classList.toggle('active',vertical);$('horizontal').classList.toggle('active',!vertical);
  $('mode-label').textContent=(vertical?'竖排':'横排')+' · 可编辑';
  $('page-count').textContent=state.view.pages.length+' 页';
  $('word-count').textContent=state.book.blocks.reduce((n,b)=>n+b.inlines.reduce((n,s)=>n+cp(s.text).length,0),0)+' 字';
  const issues=[...(state.import_warnings||[]),...state.view.issues];$('issues').hidden=!issues.length;$('issues').textContent=issues.join('　');
  const canvas=$('canvas');canvas.replaceChildren();
  state.view.pages.forEach((page,index)=>{
    const shell=document.createElement('div');shell.className='page';shell.dataset.page=index;shell.style.width=profile.width*scale+'px';
    const paper=svg('svg',{viewBox:`0 0 ${profile.width} ${profile.height}`,width:profile.width*scale,height:profile.height*scale,'aria-label':`第 ${index+1} 页`});
    paper.append(svg('rect',{width:profile.width,height:profile.height,fill:profile.paper}));
    for(const l of page.lines)paper.append(svg('line',{x1:l.x1,y1:l.y1,x2:l.x2,y2:l.y2,stroke:l.color,'stroke-width':l.width}));
    for(const p of page.polygons)paper.append(svg('polygon',{points:p.points.map(p=>p.join(',')).join(' '),fill:p.color}));
    for(const g of page.glyphs){const t=svg('text',{x:g.baseline_x,y:g.baseline_y,'font-size':g.size,fill:g.color});t.textContent=g.text;if(g.reference_id&&g.block<0){t.dataset.reference=g.reference_id;t.classList.add('reference-link');}paper.append(t);}
    if(!state.book.blocks.some(b=>b.inlines.length)&&index===0){const hint=svg('text',{x:profile.width/2,y:profile.height/2,'text-anchor':'middle',class:'empty-hint'});hint.textContent='点击纸面，开始书写';paper.append(hint);}
    paper.append(svg('g',{class:'selection-layer'}));shell.append(paper);canvas.append(shell);
    paper.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;if(event.target.dataset.reference){event.preventDefault();editNumberedNote(event.target.dataset.reference);return;}event.preventDefault();const r=paper.getBoundingClientRect(),p=localHit(index,(event.clientX-r.left)/scale,(event.clientY-r.top)/scale);
      selection=event.shiftKey?{anchor:selection.anchor,focus:p}:{anchor:p,focus:p};dragging=true;paper.setPointerCapture(event.pointerId);paintSelection();$('input').focus({preventScroll:true});
    });
    paper.addEventListener('pointermove',event=>{if(!dragging)return;const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('.page');const actual=target?Number(target.dataset.page):index;const element=target?.querySelector('svg')||paper,r=element.getBoundingClientRect();selection.focus=localHit(actual,(event.clientX-r.left)/scale,(event.clientY-r.top)/scale);paintSelection();});
    paper.addEventListener('pointerup',()=>{dragging=false;syncSelection();});
  });
  $('annotation-list').replaceChildren();state.book.annotations.forEach((note,index)=>{const item=document.createElement('div'),remove=document.createElement('button');remove.textContent='移除';remove.onclick=()=>command({type:'remove_annotation',index});item.append(remove,document.createTextNode((note.placement==='top'?'眉批：':'旁批：')+note.text));$('annotation-list').append(item);});
  (state.view.numbered_notes||[]).forEach((note,index)=>{const item=document.createElement('div'),edit=document.createElement('button');edit.textContent='编辑';edit.onclick=()=>editNumberedNote(note.target);item.append(edit,document.createTextNode(`编号 ${index+1} · ${note.label||'注文'}：${note.text}`));$('annotation-list').append(item);});
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
    if(!['undo','redo','set_metadata','set_profile','set_direction','remove_annotation','update_numbered_note','remove_numbered_note'].includes(op.type))op.selection=chosen;
    try{const next=await json('/api/command/'+id,{revision:state.revision,commands:[op]});render(next);feedback('已自动保存');$('input').focus({preventScroll:true});}
    catch(e){feedback(e.message,true);$('save-status').textContent='这次操作未保存';if(op.text){$('recovery').hidden=false;$('recovery').querySelector('textarea').value+=op.text;}if(e.message.includes('文档已更新'))render(await json('/api/document/'+id));}
  }).finally(()=>{pending--;});return queue;
}
function insertText(text){if(text)command({type:'insert_text',text,followCaret:pending>0});}
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
  if(key==='Enter'){event.preventDefault();command({type:'split_paragraph',followCaret:pending>0});return;}
  if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(key)){
    event.preventDefault();if(pending)return;
    let p=selection.focus,vertical=state.book.profile.writing_mode==='vertical-rl',i=state.block_ids.indexOf(p.block_id),text=cp(state.book.blocks[i].inlines.map(s=>s.text).join(''));
    const logical=vertical?['ArrowUp','ArrowDown']:['ArrowLeft','ArrowRight'];
    if(key==='Home')p=pos(p.block_id,0);else if(key==='End')p=pos(p.block_id,text.length);
    else if(logical.includes(key)){
      const delta=key===logical[0]?-1:1,boundaries=state.view.boundaries[p.block_id];
      let offset=delta<0?(boundaries.filter(o=>o<p.offset).pop()??-1):(boundaries.find(o=>o>p.offset)??text.length+1);
      if(offset<0&&i>0){i--;while(i>=0&&state.book.blocks[i].kind==='pagebreak')i--;if(i>=0)p=pos(state.block_ids[i],cp(state.book.blocks[i].inlines.map(s=>s.text).join('')).length);}
      else if(offset>text.length&&i<state.block_ids.length-1){i++;while(i<state.block_ids.length&&state.book.blocks[i].kind==='pagebreak')i++;if(i<state.block_ids.length)p=pos(state.block_ids[i],0);}
      else p=pos(p.block_id,Math.max(0,Math.min(text.length,offset)));
    }else{const c=caretFor(p);if(c){const profile=state.book.profile;const cross=vertical?(profile.width-2*profile.margin_x-profile.spine)/profile.panels/profile.columns:(profile.height-profile.margin_top-profile.margin_bottom)/profile.columns;p=localHit(c.page,(c.x1+c.x2)/2+(vertical?(key==='ArrowLeft'?-cross:cross):0),(c.y1+c.y2)/2+(!vertical?(key==='ArrowUp'?-cross:cross):0));}}
    selection=event.shiftKey?{anchor:selection.anchor,focus:p}:{anchor:p,focus:p};paintSelection();syncSelection();
  }
});
$('viewport').addEventListener('scroll',()=>{if(state&&selection)positionInput(caretFor(selection.focus));});

async function refreshLibrary(){const value=await json('/api/documents');$('documents').replaceChildren();for(const doc of value.documents){const button=document.createElement('button');button.className='document-item'+(state?.document_id===doc.id?' active':'');button.textContent=doc.title;button.onclick=async()=>{await queue;render(await json('/api/document/'+doc.id));};$('documents').append(button);}}
async function download(response,filename){const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function modal(title,description,fields){
  $('modal-title').textContent=title;$('modal-description').textContent=description;$('modal-fields').replaceChildren();
  for(const field of fields){
    const label=document.createElement('label');label.textContent=field.label;
    const input=document.createElement(field.options?'select':field.multiline?'textarea':'input');
    input.name=field.name;input.id='modal-'+field.name;label.htmlFor=input.id;
    if(field.options)for(const [value,name]of field.options){const o=document.createElement('option');o.value=value;o.textContent=name;input.append(o);}
    if(field.checkbox){input.type='checkbox';input.checked=!!field.value;label.className='check-row';label.prepend(input);$('modal-fields').append(label);}
    else{if(input.tagName==='INPUT')input.type=field.type||'text';input.value=field.value??'';input.required=field.required!==false;$('modal-fields').append(label,input);}
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
$('block-kind').onchange=()=>command({type:'set_block',values:{kind:$('block-kind').value}});
$('emphasis').onclick=()=>command({type:'format_range',kind:'emphasis'});$('plain').onclick=()=>command({type:'format_range',kind:'text'});
$('note').onclick=async()=>{if(!equal(selection.anchor,selection.focus)){command({type:'format_range',kind:'note'});return;}const answer=await modal('插入双行夹注','注释作为两列小字随正文排入。',[{name:'text',label:'夹注文字',multiline:true}]);if(answer)command({type:'insert_inline',kind:'note',text:answer.text});};
$('footnote').onclick=async()=>{const answer=await modal('插入脚注','Word 导出使用原生页下注；页面预览当前以随文小注显示。',[{name:'text',label:'脚注文字',multiline:true}]);if(answer)command({type:'insert_inline',kind:'footnote',text:answer.text});};
$('ruby').onclick=async()=>{if(equal(selection.anchor,selection.focus)){feedback('请先选中要加旁注的正文。',true);return;}const answer=await modal('添加短旁注','旁注与选中的正文一同流动。',[{name:'annotation',label:'旁注文字'}]);if(answer)command({type:'format_range',kind:'ruby',annotation:answer.annotation});};
$('annotation').onclick=async()=>{const answer=await modal('添加旁批或眉批','批注锚定所选文字，需要为它预留栏间或上方空间。',[{name:'placement',label:'位置',value:'side',options:[['side','栏间旁批'],['top','正文上方眉批']]},{name:'text',label:'批注文字',multiline:true}]);if(answer)command({type:'add_annotation',placement:answer.placement,text:answer.text,extent:Math.max(12,cp(answer.text).length)});};
$('label').onclick=async()=>{const a=await modal('注家标签','标签文字与边框可分别编辑。',[{name:'text',label:'标签文字',value:selectedText()||'集解'},{name:'boxed',label:'标签加框',checkbox:true,value:true}]);if(a)command({type:'insert_inline',kind:'label',text:a.text,boxed:a.boxed});};
$('numbered-note').onclick=async()=>{const a=await modal('添加编号注释','在所选文字之后插入引用。编号随注释的插入、删除自动更新。',[{name:'annotation',label:'注家标签（可选）',value:'集解',required:false},{name:'text',label:'注文',multiline:true},{name:'boxed',label:'标签加框',checkbox:true,value:true}]);if(a)command({type:'add_numbered_note',annotation:a.annotation,text:a.text,boxed:a.boxed});};
async function editNumberedNote(target){const note=(state.view.numbered_notes||[]).find(n=>n.target===target);if(!note)return;const a=await modal('编辑编号注释','正文引用与这条注文是关联对象。',[{name:'annotation',label:'注家标签（可选）',value:note.label,required:false},{name:'text',label:'注文',value:note.text,multiline:true,required:false},{name:'boxed',label:'标签加框',checkbox:true,value:note.boxed},{name:'remove',label:'移除这条注释及引用',checkbox:true,value:false}]);if(a)command(a.remove?{type:'remove_numbered_note',target}:{type:'update_numbered_note',target,text:a.text,annotation:a.annotation,boxed:a.boxed});}
async function appearance(){
  const p=state.book.profile;
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
    {name:'paper',label:'纸张颜色',type:'color',value:p.paper}]);
  const dependents=['spine_rules','fish_tail','show_title','show_volume','show_page_number'];
  for(const id of dependents)$('modal-'+id).onchange=e=>{if(e.target.checked)$('modal-spine').checked=true;};
  $('modal-spine').onchange=e=>{if(!e.target.checked)for(const id of dependents)$('modal-'+id).checked=false;};
  const clear=document.createElement('button');clear.type='button';clear.textContent='全部关闭';clear.className='element-button';clear.onclick=()=>{$('modal-border').value='none';$('modal-rules').checked=false;$('modal-spine').checked=false;for(const id of dependents)$('modal-'+id).checked=false;$('modal-paper').value='#ffffff';};$('modal-fields').append(clear);
  const a=await promise;if(!a)return;
  command({type:'set_profile',values:{border:a.border,rules:a.rules,spine:a.spine?Number(a.spine_width):0,spine_rules:a.spine_rules,fish_tail:a.fish_tail,show_title:a.show_title,show_volume:a.show_volume,show_page_number:a.show_page_number,paper:a.paper}});
}
$('appearance').onclick=appearance;$('appearance-side').onclick=appearance;
$('symbols').onclick=async()=>{
  const catalog=await json('/api/symbols'),p=state.book.profile;
  const promise=modal('鱼尾符号库','矢量符号不依赖私用区字体。选择样式后可决定是否显示。',[
    {name:'style',label:'样式',value:p.fish_tail_style||'solid',options:catalog.symbols.map(s=>[s.id,s.label])},
    {name:'direction',label:'方向',value:p.fish_tail_direction||'auto',options:[['auto','上下对应'],['down','向下'],['up','向上'],['left','向左'],['right','向右']]},
    {name:'enabled',label:'显示鱼尾',checkbox:true,value:p.fish_tail&&p.spine>0}]);
  const gallery=document.createElement('div');gallery.className='symbol-gallery';
  for(const item of catalog.symbols){const button=document.createElement('button');button.type='button';button.title=item.label;const icon=svg('svg',{viewBox:'0 0 40 40',width:40,height:40});for(const l of item.lines)icon.append(svg('line',{x1:l.x1,y1:l.y1,x2:l.x2,y2:l.y2,stroke:l.color,'stroke-width':l.width}));for(const p of item.polygons)icon.append(svg('polygon',{points:p.points.map(p=>p.join(',')).join(' '),fill:p.color}));button.append(icon,document.createTextNode(item.label));button.onclick=()=>{$('modal-style').value=item.id;};gallery.append(button);}$('modal-fields').prepend(gallery);
  const a=await promise;if(a)command({type:'set_profile',values:{fish_tail_style:a.style,fish_tail_direction:a.direction,fish_tail:a.enabled,spine:a.enabled?(p.spine||32):p.spine}});
};
$('preset').onchange=()=>command({type:'set_profile',preset:$('preset').value});
$('vertical').onclick=()=>{if(state.book.profile.writing_mode!=='vertical-rl')command({type:'set_direction',writing_mode:'vertical-rl'});};
$('horizontal').onclick=()=>{if(state.book.profile.writing_mode!=='horizontal-tb')command({type:'set_direction',writing_mode:'horizontal-tb'});};
for(const [id,key]of [['font-size','font_size'],['rows','rows'],['columns','columns'],['punctuation','punctuation']])$(id).onchange=()=>command({type:'set_profile',values:{[key]:id==='punctuation'?$(id).value:Number($(id).value)}});
$('indent').onchange=()=>command({type:'set_block',values:{indent:Number($('indent').value)}});
$('zoom').onchange=()=>{const current=structuredClone(selection);render(state);selection=current;paintSelection();};
window.addEventListener('resize',()=>{if(state&&$('zoom').value==='fit'){const current=structuredClone(selection);render(state);selection=current;paintSelection();}});
document.querySelectorAll('.toolbar button').forEach(button=>button.addEventListener('pointerdown',event=>event.preventDefault()));
(async()=>{try{const list=await json('/api/documents');render(list.documents.length?await json('/api/document/'+list.documents[0].id):await json('/api/documents',{}));await document.fonts.ready;feedback('直接点击纸面开始编辑');}catch(e){feedback(e.message,true);}})();
