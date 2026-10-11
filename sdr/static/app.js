'use strict';
const $=id=>document.getElementById(id);
let token='',timer;
const notice=text=>{$('notice').textContent=text};
async function api(path,data){const r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'X-SDR-Token':token,'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j;}
function destination(d={enabled:true,protocol:'tcp',host:'',port:10111}){
 const row=document.createElement('div');row.className='destination';
 for(const [key,label,type] of [['enabled','有効','checkbox'],['protocol','方式','select'],['host','宛先IP / ホスト','text'],['port','ポート','number']]){
  const l=document.createElement('label');l.textContent=label;const i=document.createElement(type==='select'?'select':'input');i.dataset.key=key;
  if(type==='select'){for(const v of ['tcp','udp'])i.add(new Option(v.toUpperCase(),v))}else i.type=type;
  if(type==='checkbox')i.checked=d[key];else i.value=d[key];if(key==='port'){i.min=1;i.max=65535}if(key!=='enabled')i.required=true;l.append(i);row.append(l);
 }
 const b=document.createElement('button');b.type='button';b.textContent='削除';b.onclick=()=>row.remove();row.append(b);$('destinations').append(row);
}
async function load(){const c=await api('config');for(const k of ['kind','host','port','serial','gain','ppm','sample_rate','format'])$(k).value=c.input[k];$('log_mb').value=c.log_mb;
 const files=await api('files');$('file').replaceChildren(new Option('選択してください',''));for(const f of files)$('file').add(new Option(f,f));$('file').value=c.input.file;$('destinations').replaceChildren();c.destinations.forEach(destination);
}
const names={stopped:'停止',starting:'起動中',running:'プロセス稼働',retrying:'再接続待機',finished:'ファイル処理完了',error:'エラー',unreachable:'受信サービスに接続不可'};
async function status(){try{const s=await api('status');$('summary').textContent=`${names[s.receiver.state]||s.receiver.state} ｜受信 ${s.received}文 ｜A ${s.channels.A||s.channels['1']||0} / B ${s.channels.B||s.channels['2']||0} ｜不正 ${s.invalid}文 ｜最終受信 ${s.last_received?new Date(s.last_received*1000).toLocaleString():'未受信'}`;
 $('diagnostics').textContent=(s.receiver.diagnostics||[]).join('\n');$('outputs').replaceChildren();for(const d of s.destinations){const div=document.createElement('div');div.className='output';div.textContent=`${d.protocol.toUpperCase()} ${d.host}:${d.port} ｜${d.connected?'接続中':'未接続'} ｜送信 ${d.sent} ｜破棄 ${d.dropped} ｜接続エラー ${d.failures} ${d.error}`;$('outputs').append(div)}
 }catch(e){notice(e.message)}}
$('login').onsubmit=async e=>{e.preventDefault();token=$('token').value;try{await load();$('controls').hidden=false;notice('接続しました');clearInterval(timer);await status();timer=setInterval(status,2000)}catch(e){notice(e.message)}};
$('add').onclick=()=>{if($('destinations').children.length<16)destination();else notice('最大16件です')};
$('settings').onsubmit=async e=>{e.preventDefault();const input={};for(const k of ['kind','host','port','serial','gain','ppm','sample_rate','format','file'])input[k]=$(k).value;for(const k of ['port','ppm','sample_rate'])input[k]=Number(input[k]);if(input.gain!=='auto')input.gain=Number(input.gain);
 const destinations=[...$('destinations').children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-key]')].map(i=>[i.dataset.key,i.type==='checkbox'?i.checked:i.type==='number'?Number(i.value):i.value])));
 try{await api('config',{input,destinations,log_mb:Number($('log_mb').value)});notice('保存しました。受信開始を押してください。');await status()}catch(e){notice(e.message)}};
for(const action of ['start','stop','reconnect'])$(action).onclick=async()=>{const b=$(action);b.disabled=true;try{await api(action,{});notice('操作を受け付けました');await status()}catch(e){notice(e.message)}finally{b.disabled=false}};
$('logs').onclick=async()=>{try{const files=await api('logs');$('downloads').replaceChildren();for(const name of files){const b=document.createElement('button');b.textContent=name;b.onclick=async()=>{try{const r=await fetch('/api/logs/'+name,{headers:{'X-SDR-Token':token}});if(!r.ok)throw Error('ログ取得失敗');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){notice(e.message)}};$('downloads').append(b)}}catch(e){notice(e.message)}};
