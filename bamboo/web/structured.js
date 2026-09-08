'use strict';
let structuredDraft=null;
const structuredNames={gift:'礼簿',genealogy:'族谱',gongche:'工尺谱'};
function structuredFields(kind){
 if(kind==='genealogy')return [{key:'name',label:'姓名',required:true},{key:'parents',label:'父母（可多选）',relation:true,value:[]},{key:'spouses',label:'配偶（可多选）',relation:true,value:[]},{key:'birth',label:'生年'},{key:'death',label:'卒年'},{key:'biography',label:'人物传记',multiline:true}];
 return [{key:'name',label:'姓名',required:true},{key:'amount',label:'礼金（元）',value:'0.00',required:true},{key:'gift',label:'礼品'},{key:'date',label:'日期',type:'date'},{key:'note',label:'备注',multiline:true}];
}
function moneyPreview(){
 if(structuredDraft.kind==='genealogy'){$('structured-summary').textContent=structuredDraft.records.length+' 位人物 · 保存后计算世代并生成世系图与人物传记';return;}
 let cents=0n,valid=true;
 for(const r of structuredDraft.records){if(!/^\d{1,12}(\.\d{1,2})?$/.test(r.amount||'')){valid=false;break;}const [a,b='']=r.amount.split('.');cents+=BigInt(a)*100n+BigInt(b.padEnd(2,'0'));}
 $('structured-summary').textContent=structuredDraft.records.length+' 条记录'+(valid?' · 礼金合计 '+(cents/100n)+'.'+(cents%100n).toString().padStart(2,'0')+' 元':' · 请填写有效金额');
}
function paintStructured(){
 const fields=structuredFields(structuredDraft.kind),table=document.createElement('table'),thead=document.createElement('thead'),head=document.createElement('tr');
 for(const title of [...fields.map(f=>f.label),'操作']){const th=document.createElement('th');th.textContent=title;head.append(th);}thead.append(head);table.append(thead);const body=document.createElement('tbody');
 for(const [index,record]of structuredDraft.records.entries()){
  const row=document.createElement('tr');row.dataset.record=record.id;
  for(const f of fields){
   const cell=document.createElement('td'),input=document.createElement(f.relation?'select':f.multiline?'textarea':'input');input.dataset.field=f.key;input.setAttribute('aria-label',f.label+' '+(index+1));
   if(f.relation){input.multiple=true;input.size=3;for(const [oi,other]of structuredDraft.records.entries()){if(other.id===record.id)continue;const option=document.createElement('option');option.value=other.id;option.dataset.person=other.id;option.textContent=(oi+1)+' '+(other.name||'未命名人物');option.selected=(record[f.key]||[]).includes(other.id);input.append(option);}}
   else{input.value=record[f.key]??f.value??'';if(f.required)input.required=true;if(input.tagName==='INPUT')input.type=f.type||'text';if(f.key==='amount')input.inputMode='decimal';}
   input.oninput=()=>{record[f.key]=f.relation?Array.from(input.selectedOptions).map(o=>o.value):input.value;if(f.key==='name')$('structured-records').querySelectorAll(`[data-person="${record.id}"]`).forEach(o=>o.textContent=(index+1)+' '+input.value);moneyPreview();};cell.append(input);row.append(cell);
  }
  const actions=document.createElement('td');
  for(const [label,delta]of [['上移',-1],['下移',1],['删除',0]]){const button=document.createElement('button');button.type='button';button.textContent=label;button.disabled=delta===-1&&index===0||delta===1&&index===structuredDraft.records.length-1;button.onclick=()=>{if(delta){const records=structuredDraft.records;[records[index],records[index+delta]]=[records[index+delta],records[index]];}else{structuredDraft.records.splice(index,1);if(structuredDraft.kind==='genealogy')for(const person of structuredDraft.records)for(const key of ['parents','spouses'])person[key]=person[key].filter(id=>id!==record.id);}paintStructured();};actions.append(button);}
  row.append(actions);body.append(row);
 }
 table.append(body);$('structured-records').replaceChildren(table);moneyPreview();
}
async function openStructured(kind,recordId,field){
 try{await queue;if(state.book.special?.kind!==kind)render(await json('/api/documents',{kind}));
  structuredDraft=structuredClone(state.book.special);
  $('structured-intro').textContent=kind==='genealogy'?'录入人物，选择父母和配偶，自动生成世系图与传记。删除人物时会移除其关联，保存后仍可撤销。':'逐条录入，自动计算金额大写和合计。';
  $('structured-cap-label').firstChild.nodeValue=kind==='genealogy'?'每张世系图人数':'每页最多记录';$('structured-cap').max=kind==='genealogy'?12:20;
  $('structured-heading').textContent=structuredNames[kind];$('structured-title').value=state.book.title;$('structured-direction').value=state.book.profile.writing_mode;$('structured-occasion').value=structuredDraft.occasion||'';$('structured-date').value=structuredDraft.date||'';$('structured-cap').value=structuredDraft.per_page||6;$('structured-error').textContent='';paintStructured();$('structured-dialog').showModal();
  if(recordId){const row=Array.from($('structured-records').querySelectorAll('tr')).find(r=>r.dataset.record===recordId);row?.querySelector(`[data-field="${field==='uppercase'?'amount':field||'name'}"]`)?.focus();}
 }catch(e){feedback(e.message,true);}
}
$('gift-book').onclick=()=>openStructured('gift');
$('family-book').onclick=()=>openStructured('genealogy');
$('structured-add').onclick=()=>{const record={id:crypto.randomUUID().replaceAll('-','')};for(const f of structuredFields(structuredDraft.kind))record[f.key]=structuredClone(f.value??'');structuredDraft.records.push(record);paintStructured();$('structured-records').querySelector('tbody tr:last-child input')?.focus();};
for(const id of ['structured-close','structured-cancel'])$(id).onclick=()=>$('structured-dialog').close();
$('structured-form').onsubmit=event=>{
 event.preventDefault();const value=structuredClone(structuredDraft);value.occasion=$('structured-occasion').value;value.date=$('structured-date').value;value.per_page=Number($('structured-cap').value);
 const title=$('structured-title').value,direction=$('structured-direction').value,id=state.document_id;
 $('structured-save').disabled=true;$('structured-error').textContent='';
 queue=queue.then(async()=>{try{const result=await json('/api/command/'+id,{revision:state.revision,commands:[{type:'set_special',value},{type:'set_metadata',values:{title}},{type:'set_direction',writing_mode:direction}]});render(result);$('structured-dialog').close();feedback('已保存并重新排版');}catch(e){$('structured-error').textContent=e.message;}}).finally(()=>{$('structured-save').disabled=false;});
};
