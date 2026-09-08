'use strict';
let structuredDraft=null;
const structuredNames={gift:'册簿',genealogy:'族谱',gongche:'工尺谱'};
function structuredFields(kind){
 if(kind==='gongche')return [{key:'phrase',label:'分句',value:'第一句',required:true},{key:'symbol',label:'谱字',required:true,options:['合','四','一','上','尺','工','凡','六','五','乙']},{key:'beat',label:'板眼',options:['板','头眼','中眼','末眼','散板','●','○','×','·']},{key:'register',label:'音区标注',options:['高','低']},{key:'lyric',label:'唱词',multiline:true},{key:'lyric_span',label:'唱词对应谱字数',type:'number',numeric:true,value:1,required:true}];
 if(kind==='genealogy')return [{key:'name',label:'姓名',required:true},{key:'parents',label:'父母（可多选）',relation:true,value:[]},{key:'spouses',label:'配偶（可多选）',relation:true,value:[]},{key:'birth',label:'生年'},{key:'death',label:'卒年'},{key:'biography',label:'人物传记',multiline:true}];
 return [{key:'name',label:'姓名',required:true},{key:'amount',label:'金额（元）',value:'0.00',required:true},{key:'gift',label:'物品'},{key:'date',label:'日期',type:'date'},{key:'note',label:'备注',multiline:true}];
}
function moneyPreview(){
 if(structuredDraft.kind==='gongche'){$('structured-summary').textContent=structuredDraft.records.length+' 个谱字 · 一字多音时填写起始唱词，后续对应谱字的唱词留空';return;}
 if(structuredDraft.kind==='genealogy'){$('structured-summary').textContent=structuredDraft.records.length+' 位人物 · 保存后计算世代并生成世系图与人物传记';return;}
 let cents=0n,valid=true;
 for(const r of structuredDraft.records){if(!/^\d{1,12}(\.\d{1,2})?$/.test(r.amount||'')){valid=false;break;}const [a,b='']=r.amount.split('.');cents+=BigInt(a)*100n+BigInt(b.padEnd(2,'0'));}
 $('structured-summary').textContent=structuredDraft.records.length+' 条记录'+(valid?' · 金额合计 '+(cents/100n)+'.'+(cents%100n).toString().padStart(2,'0')+' 元':' · 请填写有效金额');
}
function scoreAtoms(){const result=[];let start=0;while(start<structuredDraft.records.length){const span=Math.max(1,Math.min(Number(structuredDraft.records[start].lyric_span)||1,structuredDraft.records.length-start));result.push({start,span});start+=span;}return result;}
function scoreAtom(index){return scoreAtoms().find(a=>a.start<=index&&index<a.start+a.span);}
function moveScore(index,delta){const atoms=scoreAtoms(),at=atoms.findIndex(a=>a.start<=index&&index<a.start+a.span),to=at+delta;if(to<0||to>=atoms.length)return;const groups=atoms.map(a=>structuredDraft.records.slice(a.start,a.start+a.span));[groups[at],groups[to]]=[groups[to],groups[at]];structuredDraft.records=groups.flat();}
function deleteScore(index){const atom=scoreAtom(index),records=structuredDraft.records;if(atom&&atom.span>1){if(index===atom.start){records[index+1].lyric=records[index].lyric;records[index+1].lyric_span=atom.span-1;}else records[atom.start].lyric_span=atom.span-1;}records.splice(index,1);}
function paintStructured(){
 const fields=structuredFields(structuredDraft.kind),table=document.createElement('table'),thead=document.createElement('thead'),head=document.createElement('tr');
 for(const title of [...fields.map(f=>f.label),'操作']){const th=document.createElement('th');th.textContent=title;head.append(th);}thead.append(head);table.append(thead);const body=document.createElement('tbody');
 for(const [index,record]of structuredDraft.records.entries()){
  const row=document.createElement('tr');row.dataset.record=record.id;
  for(const f of fields){
   const cell=document.createElement('td'),input=document.createElement(f.relation?'select':f.multiline?'textarea':'input');input.dataset.field=f.key;input.setAttribute('aria-label',f.label+' '+(index+1));
   if(f.relation){input.multiple=true;input.size=3;for(const [oi,other]of structuredDraft.records.entries()){if(other.id===record.id)continue;const option=document.createElement('option');option.value=other.id;option.dataset.person=other.id;option.textContent=(oi+1)+' '+(other.name||'未命名人物');option.selected=(record[f.key]||[]).includes(other.id);input.append(option);}}
   else{input.value=record[f.key]??f.value??'';if(f.required)input.required=true;if(input.tagName==='INPUT')input.type=f.type||'text';if(f.key==='amount')input.inputMode='decimal';if(f.numeric){input.min=1;input.max=16;input.step=1;}}
   input.oninput=()=>{record[f.key]=f.relation?Array.from(input.selectedOptions).map(o=>o.value):f.numeric?Number(input.value):input.value;if(f.key==='phrase'&&structuredDraft.kind==='gongche'){const atom=scoreAtom(index);for(let i=atom.start;i<atom.start+atom.span;i++){structuredDraft.records[i].phrase=input.value;$('structured-records').querySelector(`[data-record="${structuredDraft.records[i].id}"] [data-field=phrase]`).value=input.value;}}if(f.key==='name')$('structured-records').querySelectorAll(`[data-person="${record.id}"]`).forEach(o=>o.textContent=(index+1)+' '+input.value);moneyPreview();};cell.append(input);if(f.options){const list=document.createElement('datalist');list.id='special-options-'+index+'-'+f.key;for(const value of f.options){const option=document.createElement('option');option.value=value;list.append(option);}input.setAttribute('list',list.id);cell.append(list);}row.append(cell);
  }
  const actions=document.createElement('td');
  for(const [label,delta]of [['上移',-1],['下移',1],['删除',0]]){const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=delta===-1&&index===0||delta===1&&index===structuredDraft.records.length-1;button.onclick=()=>{if(structuredDraft.kind==='gongche'){if(delta)moveScore(index,delta);else deleteScore(index);paintStructured();return;}if(delta){const records=structuredDraft.records;[records[index],records[index+delta]]=[records[index+delta],records[index]];}else{structuredDraft.records.splice(index,1);if(structuredDraft.kind==='genealogy')for(const person of structuredDraft.records)for(const key of ['parents','spouses'])person[key]=person[key].filter(id=>id!==record.id);}paintStructured();};actions.append(button);}
  row.append(actions);body.append(row);
 }
 table.append(body);$('structured-records').replaceChildren(table);moneyPreview();
}
async function openStructured(kind,recordId,field){
 try{await queue;if(state.book.special?.kind!==kind)render(await json('/api/documents',{kind}));
  structuredDraft=structuredClone(state.book.special);
  $('structured-intro').textContent=kind==='gongche'?'录入谱字、板眼、音区和唱词，可填写原谱记号。一字多音的后续唱词留空；上下移动按对应组整体移动，删除谱字时保留其余对应关系。':kind==='genealogy'?'录入人物，选择父母和配偶，自动生成世系图与传记。删除人物时会移除其关联，保存后仍可撤销。':'逐条录入，自动计算金额大写和合计。';
  $('structured-cap-label').firstChild.nodeValue=kind==='gongche'?'每组最多谱字':kind==='genealogy'?'每张世系图人数':'每页最多记录';$('structured-cap').max=kind==='gongche'?16:kind==='genealogy'?12:20;$('structured-systems-label').hidden=kind!=='gongche';$('structured-systems').value=structuredDraft.systems_per_page||3;
  $('structured-heading').textContent=structuredNames[kind];$('structured-title').value=state.book.title;$('structured-direction').value=state.book.profile.writing_mode;$('structured-occasion').value=structuredDraft.occasion||'';$('structured-date').value=structuredDraft.date||'';$('structured-cap').value=structuredDraft.per_page||6;$('structured-error').textContent='';paintStructured();$('structured-dialog').showModal();
  if(recordId){const row=Array.from($('structured-records').querySelectorAll('tr')).find(r=>r.dataset.record===recordId);row?.querySelector(`[data-field="${field==='uppercase'?'amount':field||'name'}"]`)?.focus();}
 }catch(e){feedback(e.message,true);}
}
$('gift-book').onclick=()=>openStructured('gift');
$('family-book').onclick=()=>openStructured('genealogy');
$('gongche-book').onclick=()=>openStructured('gongche');
$('structured-add').onclick=()=>{const record={id:crypto.randomUUID().replaceAll('-','')};for(const f of structuredFields(structuredDraft.kind))record[f.key]=structuredClone(f.value??'');if(structuredDraft.kind==='gongche'&&structuredDraft.records.length)record.phrase=structuredDraft.records[structuredDraft.records.length-1].phrase;structuredDraft.records.push(record);paintStructured();$('structured-records').querySelector('tbody tr:last-child input')?.focus();};
for(const id of ['structured-close','structured-cancel'])$(id).onclick=()=>$('structured-dialog').close();
$('structured-form').onsubmit=event=>{
 event.preventDefault();const value=structuredClone(structuredDraft);value.occasion=$('structured-occasion').value;value.date=$('structured-date').value;value.per_page=Number($('structured-cap').value);if(value.kind==='gongche')value.systems_per_page=Number($('structured-systems').value);
 const title=$('structured-title').value,direction=$('structured-direction').value,id=state.document_id;
 $('structured-save').disabled=true;$('structured-error').textContent='';
 queue=queue.then(async()=>{try{const result=await json('/api/command/'+id,{revision:state.revision,commands:[{type:'set_special',value},{type:'set_metadata',values:{title}},{type:'set_direction',writing_mode:direction}]});render(result);$('structured-dialog').close();feedback('已保存并重新排版');}catch(e){$('structured-error').textContent=e.message;}}).finally(()=>{$('structured-save').disabled=false;});
};
