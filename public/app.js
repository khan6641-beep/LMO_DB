'use strict';
const content=document.querySelector('#content'), dialog=document.querySelector('#record-dialog');
const groups={plants:'Plants',arthropods:'Arthropods'};
const precisions={year:'year',month:'month',day:'day'};
const types={presence_label:'Presence / list',individual_count:'Individuals'};
const state={tab:'overview',filters:{},page:1,issuePage:1,issueStatus:'open',weatherPage:1,weatherYear:2026,station:'614',metric:'temperature_max_c'};
let boot,weatherRows=[],schemaSVG='',record;
const h=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>v===null||v===undefined?'Missing':typeof v==='number'?Number(v.toPrecision(8)).toLocaleString('en-US',{maximumSignificantDigits:8}):h(v);
const count=v=>Number(v).toLocaleString('en-US');
const options=(rows,value,label,selected='')=>rows.map(r=>`<option value="${h(r[value])}" ${String(r[value])===String(selected)?'selected':''}>${h(r[label])}</option>`).join('');
const field=(label,id,control,klass='')=>`<div class="field ${klass}"><label for="${id}">${label}</label>${control}</div>`;
const table=(headers,rows,klass='')=>`<div class="table-wrap" tabindex="0" aria-label="Data table"><table class="${klass}"><thead><tr>${headers.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(row=>`<tr>${row.map(x=>`<td>${x}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">No matching records.</td></tr>`}</tbody></table></div>`;
async function api(path,body){
 const response=await fetch('/api/'+path,body?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':boot.token},body:JSON.stringify(body)}:{});
 const data=await response.json();if(!response.ok)throw new Error(data.error||'Request failed.');return data;
}
function toast(message){const e=document.querySelector('#toast');e.textContent=message;e.hidden=false;setTimeout(()=>e.hidden=true,5000);}
function fail(error,inside=false){const e=inside?document.querySelector('#detail-error'):document.querySelector('#global-error');if(e){e.textContent=error.message;e.hidden=false;}else toast(error.message);}
function facts(rows){return `<dl class="facts">${rows.map(([a,b])=>`<dt>${h(a)}</dt><dd>${b}</dd>`).join('')}</dl>`;}
function formData(form){return Object.fromEntries(new FormData(form));}
function query(){return new URLSearchParams({...state.filters,page:state.page}).toString();}
async function show(tab=state.tab){
 state.tab=tab;document.querySelectorAll('[data-tab]').forEach(b=>{if(b.dataset.tab===tab)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
 document.querySelector('#global-error').hidden=true;content.innerHTML='<p role="status">Loading database...</p>';
 try{await ({overview,observations,quality,weather,experiments,aerial,registry,import:imports,schema,history})[tab]();}
 catch(error){content.innerHTML='<p>Unable to load data. Select the menu again or reload the page.</p>';fail(error);}
}
async function overview(){
 const s=await api('summary');
 content.innerHTML=`<h1>Database overview</h1><p class="lede">Plant and arthropod observations, experiment designs, weather series and the aerial inventory of the confined field.</p>
 <div class="split"><section><h2>Records by data group</h2>${table(['Data group','Records','Taxon label IDs'],s.groups.map(r=>[h(groups[r.group_name]),count(r.records),count(r.labels)]))}
 <h2>Observation period</h2>${table(['Survey year','Records'],s.years.map(r=>[h(r.year),count(r.records)]))}</section>
 <section><h2>Provenance and verification</h2>${facts([['Total observation records',count(s.observations)],['Data sources',count(s.sources)+' items'],['Experiments',count(s.experiments)],['Measurement slots',count(s.measurement_slots)+' ('+count(s.measured_values)+' entered)'],['Date verification',count(s.dated)+' records'],['Survey events',count(s.events)+' records'],['Samples',count(s.samples)+' records'],['Unresolved cells',count(s.unresolved_cells)+' items'],['Open review issues',count(s.issues_open)+' records']])}
 <h2>Time precision</h2>${table(['Category','Records'],s.time_precision.map(r=>[h(precisions[r.precision]||r.precision),count(r.records)]))}</section></div>
 <h2>Weather availability</h2>${table(['Station','Date records','Temperature valid days','Humidity valid days','Rainfall valid days'],s.weather.map(r=>[`${h(r.name)} ${h(r.station_id)}`,count(r.dates),count(r.mean_temperature_days),count(r.humidity_days),count(r.rain_days)]))}
 <p class="notice">Station series are stored separately. Availability and verification status accompany each observation.</p>
 <div class="actions"><button data-tab="observations">Browse observations</button><a class="download secondary" href="/api/backup">Download DB backup</a></div>`;
}
async function observations(){
 const data=await api('observations?'+query()),f=state.filters;
 content.innerHTML=`<h1>Observations</h1><p class="lede">Search original measurements and taxon labels; link verified dates, plots and samples.</p>
 <form id="filters" class="toolbar">${field('Taxon search','search-q',`<input id="search-q" name="q" value="${h(f.q)}" placeholder="Scientific or common name">`,'search')}
 ${field('Data group','filter-group',`<select id="filter-group" name="group"><option value="">All</option>${Object.entries(groups).map(([k,v])=>`<option value="${k}" ${f.group===k?'selected':''}>${v}</option>`).join('')}</select>`)}
 ${field('Survey year','filter-year',`<select id="filter-year" name="year"><option value="">All</option>${boot.years.map(y=>`<option ${String(f.year)===String(y)?'selected':''}>${y}</option>`).join('')}</select>`)}
 ${field('Survey month','filter-month',`<select id="filter-month" name="month"><option value="">All</option>${Array.from({length:12},(_,i)=>`<option value="${i+1}" ${Number(f.month)===i+1?'selected':''}>Month ${i+1}</option>`).join('')}</select>`)}
 ${field('Data source','filter-source',`<select id="filter-source" name="source"><option value="">All</option>${boot.sources.map(r=>`<option value="${r.id}" ${Number(f.source)===r.id?'selected':''}>${h(r.id+' · '+r.name.replace('Dataset on the distribution of ','').replace('Dataset on distribution characteristics of ',''))}</option>`).join('')}</select>`,'source-filter')}
 <button type="submit">Search</button><button type="button" class="secondary" id="reset-filters">Reset</button></form>
 <div class="pagination"><span>Matching records: ${count(data.total)} records</span><a class="download secondary" href="/api/export?${h(new URLSearchParams(f))}">Export selection</a></div>
 ${table(['Record','Data group','Taxon label','Observation time','Type','Value','Original position',''],data.rows.map(r=>[h(r.id),h(groups[r.group_name]),`<span class="name">${h(r.scientific_name||r.label||r.korean_name)}</span>`,h(r.survey_date||`${r.survey_year}${r.survey_month?'-'+String(r.survey_month).padStart(2,'0'):''}`)+`<br><span class="muted">${h(precisions[r.time_precision])} precision</span>`,h(types[r.measurement_type]),r.value!==null?num(r.value)+' '+h(r.unit):h(r.raw_value==='Y'?'Present':r.raw_value||'List entry'),h(`Source ${r.source_id} · Row ${r.row_number}${r.source_column?' · Column '+r.source_column:''}`),`<button class="small-button secondary" data-record="${r.id}">Open record</button>`]),'record-table')}
 <div class="pagination"><button id="prev-records" class="secondary" ${data.page===1?'disabled':''}>Previous</button><span>${data.page} / ${Math.max(1,Math.ceil(data.total/data.size))} page</span><button id="next-records" class="secondary" ${data.page*data.size>=data.total?'disabled':''}>Next</button></div>`;
}
async function openRecord(id){
 record=await api('observation?id='+id);const r=record;
 document.querySelector('#record-title').textContent=`Record ${r.id} · ${r.scientific_name||r.label||r.korean_name}`;
 document.querySelector('#record-content').innerHTML=`<div id="detail-error" class="error" role="alert" hidden></div><div class="split"><section><h3>Observation and original data</h3>${facts([['Data group',h(groups[r.group_name])],['Taxon label',h(r.label)],['Measurement type',h(types[r.measurement_type])],['Stored value',r.value===null?h(r.raw_value||'List entry'):num(r.value)+' '+h(r.unit)],['Original text',h(r.raw_value||'Not provided')],['Time precision',h(precisions[r.time_precision])],['Survey date',h(r.survey_date||'Unverified')],['Original position',`Row ${r.row_number} / Column ${r.source_column||'Single header'}`],['Coordinate status',h(r.coordinate_status||'Not provided')]])}
 <details><summary>Source and hash</summary><p>${h(r.source_name)}</p><pre>${h(r.source_sha256)}</pre></details>
 <details><summary>Original row cells: ${r.raw_cells.length} items</summary><pre>${h(JSON.stringify(r.raw_cells.map((value,i)=>({column:i+1,value})),null,2))}</pre></details>
 <h3>Weather observations</h3><p class="muted">${r.survey_date?'Station observations for the verified survey date.':r.survey_month?'Monthly station summary with available-day counts.':'Annual station summary with available-day counts.'}</p>
 ${table(['Station','Mean temperature','Mean humidity','Valid days'],r.weather.map(w=>[h(w.station_name),num(w.temperature_mean_c??w.temperature_observed_daily_mean_c)+' °C',num(w.humidity_mean_pct??w.humidity_observed_daily_mean_pct)+' %',r.survey_date?'Daily data':`${w.temperature_valid_days} / ${w.humidity_valid_days} (temperature / humidity)`]))}</section>
 <section><h3>Link survey information</h3><p class="muted">Enter verified dates and identifiers. Dates must match the existing year and month.</p>
 <form id="context-form" class="form-grid">${field('Verified survey date','context-date',`<input id="context-date" type="date" name="survey_date" value="${h(r.survey_date)}" required>`)}
 ${field('Scope','context-scope',`<select id="context-scope" name="scope"><option value="single">This record</option>${r.source_column?`<option value="column">Same source column: ${r.column_records} records</option>`:''}</select>`)}
 ${field('Facility','context-facility',`<select id="context-facility" name="facility_id"><option value="">Unspecified</option>${options(boot.facilities,'id','name',r.context?.facility_id)}</select>`)}
 ${field('Plot','context-plot',`<select id="context-plot" name="plot_id"><option value="">Unspecified</option>${options(boot.plots,'id','code',r.context?.plot_id)}</select>`)}
 ${field('Sample code (optional)','sample-code',`<input id="sample-code" name="sample_code" value="${h(r.context?.sample_code)}" placeholder="Verified code">`)}
 ${field('Method (optional)','context-method',`<input id="context-method" name="method" placeholder="Verified method">`)}
 <div class="span-two"><label for="context-reason">Evidence</label><textarea id="context-reason" name="reason" required placeholder="Record the evidence for the date and sample assignment"></textarea></div><button type="submit" class="span-two">Save survey information</button></form>
 <h3>Review taxon names</h3><p class="muted">Records with taxon ID ${r.taxon_id} share this update; the original label is retained.</p>
 <form id="taxon-form" class="form-grid">${field('Scientific name','taxon-scientific',`<input id="taxon-scientific" name="scientific_name" value="${h(r.scientific_name)}">`)}${field('Common name','taxon-korean',`<input id="taxon-korean" name="korean_name" value="${h(r.korean_name)}">`)}
 <div class="span-two"><label for="taxon-rank">Rank or verification status</label><input id="taxon-rank" name="rank_status" value="${h(r.rank_status)}" required></div>
 <div class="span-two"><label for="taxon-reason">Name verification evidence</label><textarea id="taxon-reason" name="reason" required></textarea></div><button type="submit" class="secondary span-two">Save taxon review</button></form></section></div>
 <h3>Record revisions</h3>${table(['Time UTC','Changed field','Evidence'],r.revisions.map(x=>[h(x.changed_at),h(x.field_name),h(x.reason)]))}`;
 if(!dialog.open)dialog.showModal();
}
async function quality(){
 const data=await api(`issues?status=${state.issueStatus}&page=${state.issuePage}`);
 content.innerHTML=`<h1>Review</h1><p class="lede">Review issues by source and original column. Review status and data amendments are recorded separately.</p>
 <div class="toolbar">${field('Review status','issue-status',`<select id="issue-status"><option value="open" ${state.issueStatus==='open'?'selected':''}>Pending</option><option value="reviewed" ${state.issueStatus==='reviewed'?'selected':''}>Reviewed</option></select>`)}<span>${count(data.total)} issues</span></div>
 ${table(['Item','Source position','Issue','Affected records','Review'],data.rows.map(r=>[h(r.id),h(`Source ${r.source_id}${r.source_column?' / Column '+r.source_column:''}`),`${h(r.description)}<br><span class="muted">${h(r.code)}</span>${r.note?'<p>'+h(r.note)+'</p>':''}`,count(r.affected_count),`<form class="review-form" data-id="${r.id}"><label for="note-${r.id}">Review evidence</label><input id="note-${r.id}" name="note" required><button class="small-button secondary">Save review</button></form>${r.code==='unresolved_cell'?`<button class="small-button secondary" data-unresolved="${r.source_id}">View unresolved cells</button>`:''}`]))}
 <div id="unresolved-view"></div><div class="pagination"><button class="secondary" id="prev-issues" ${data.page===1?'disabled':''}>Previous</button><span>${data.page} / ${Math.max(1,Math.ceil(data.total/30))}</span><button class="secondary" id="next-issues" ${data.page*30>=data.total?'disabled':''}>Next</button></div>`;
}
const metrics={temperature_max_c:['Maximum temperature','°C'],temperature_min_c:['Minimum temperature','°C'],temperature_mean_c:['Mean temperature','°C'],precipitation_mm:['Daily precipitation','mm'],humidity_mean_pct:['Mean relative humidity','%'],wind_mean_ms:['Mean wind speed','m/s'],pressure_mean_hpa:['Mean station pressure','hPa']};
function chart(rows,key){
 const valid=rows.filter(r=>r[key]!==null),values=valid.map(r=>r[key]);if(!values.length)return '<p>No valid observations for this station, year and variable.</p>';
 let lo=Math.min(...values),hi=Math.max(...values);if(lo===hi){lo-=1;hi+=1;}const y=v=>250-(v-lo)/(hi-lo)*210,x=i=>65+i/Math.max(1,rows.length-1)*930;
 let paths=[],path='';rows.forEach((r,i)=>{if(r[key]===null){if(path)paths.push(path);path='';}else path+=`${path?'L':'M'}${x(i).toFixed(2)},${y(r[key]).toFixed(2)} `;});if(path)paths.push(path);
 return `<svg class="chart" viewBox="0 0 1040 300" role="img" aria-label="${h(metrics[key][0])} daily observations. Gaps retain missing values."><title>${h(metrics[key][0])} ${state.weatherYear} year</title><g fill="#52635a" font-size="14" font-family="sans-serif"><text x="5" y="48">${num(hi)}</text><text x="5" y="253">${num(lo)}</text><text x="65" y="285">${h(rows[0].date)}</text><text x="875" y="285">${h(rows.at(-1).date)}</text></g><path d="M65,40V250H995" stroke="#9aac9e" fill="none"/>${paths.map(p=>`<path d="${p}" fill="none" stroke="#1f6f43" stroke-width="2"/>`).join('')}${rows.map((r,i)=>r[key]===null?'':`<circle cx="${x(i)}" cy="${y(r[key])}" r="1.8" fill="#1f6f43"><title>${h(r.date)}: ${num(r[key])} ${h(metrics[key][1])}</title></circle>`).join('')}</svg>`;
}
async function weather(){
 const data=await api(`weather?station=${state.station}&year=${state.weatherYear}`);weatherRows=data.rows;
 content.innerHTML=`<h1>Weather</h1><p class="lede">Explore the Seocheon AWS and Gunsan ASOS series separately. Missing values are retained.</p>
 <div class="toolbar">${field('Station','weather-station',`<select id="weather-station">${options(boot.stations,'station_id','name',state.station)}</select>`)}${field('Observation year','weather-year',`<select id="weather-year">${[2019,2020,2021,2022,2023,2024,2025,2026].map(y=>`<option ${y===state.weatherYear?'selected':''}>${y}</option>`).join('')}</select>`)}${field('Graph variable','weather-metric',`<select id="weather-metric">${Object.entries(metrics).map(([k,v])=>`<option value="${k}" ${k===state.metric?'selected':''}>${h(v[0])} ${h(v[1])}</option>`).join('')}</select>`)}</div>
 <p>${h(data.station.name)} ${h(data.station.station_id)} · ${h(data.station.provider)} · Valid values: ${data.rows.filter(r=>r[state.metric]!==null).length} / ${data.rows.length}day</p><div class="chart-wrap">${chart(data.rows,state.metric)}</div>
 <p class="notice">Seocheon mean variables are calculated from minute observations. Station series and quality information are preserved separately.</p>
 <h2>Daily observations</h2><div id="weather-table"></div><div class="pagination"><button id="prev-weather" class="secondary">Previous</button><span id="weather-page"></span><button id="next-weather" class="secondary">Next</button></div>
 <h2>Monthly summaries and availability</h2>${table(['month','Mean temperature','Mean humidity','Temperature / humidity valid days','Observed rainfall sum','Rainfall valid days'],data.monthly.map(r=>['Month '+r.month,num(r.temperature_observed_daily_mean_c)+' °C',num(r.humidity_observed_daily_mean_pct)+' %',`${r.temperature_valid_days} / ${r.humidity_valid_days}`,num(r.precipitation_observed_sum_mm)+' mm',`${r.precipitation_valid_days} / ${r.calendar_days}`]))}<p class="muted">Summaries report available daily values and their valid-day counts.</p>`;weatherTable();
}
function weatherTable(){
 const max=Math.max(1,Math.ceil(weatherRows.length/30));state.weatherPage=Math.min(max,state.weatherPage);
 document.querySelector('#weather-table').innerHTML=table(['Date','Mean / min / max temperature °C','Rainfall mm','Mean humidity %','Wind m/s','Pressure hPa','Quality status'],weatherRows.slice((state.weatherPage-1)*30,state.weatherPage*30).map(r=>{const qc=JSON.parse(r.qc_json||'{}');return [h(r.date),`${num(r.temperature_mean_c)} / ${num(r.temperature_min_c)} / ${num(r.temperature_max_c)}`,num(r.precipitation_mm),num(r.humidity_mean_pct),num(r.wind_mean_ms),num(r.pressure_mean_hpa),`<details><summary>${qc.minute_fetch_status==='not_complete'?'Minute statistics pending':qc.coverage_flags&&Object.values(qc.coverage_flags).some(v=>v!=='complete')?'Partial observations':'Daily statistics / verified collection'}</summary><pre>${h(JSON.stringify(qc,null,2))}</pre></details>`];}));
 document.querySelector('#weather-page').textContent=`${state.weatherPage} / ${max}`;document.querySelector('#prev-weather').disabled=state.weatherPage===1;document.querySelector('#next-weather').disabled=state.weatherPage===max;
}
async function registry(){
 content.innerHTML=`<h1>Facilities and plots</h1><p class="lede">Register verified facility names, plot codes and treatment assignments.</p><div class="split"><section class="registry-section"><h2>Register facility</h2><form id="facility-form"><label for="facility-name">Facility name</label><input id="facility-name" name="name" required><label for="facility-description">Description</label><textarea id="facility-description" name="description"></textarea><button>Save facility</button></form><h3>Facilities</h3>${table(['ID','Facility name','Description'],boot.facilities.map(r=>[r.id,h(r.name),h(r.description)]))}</section>
 <section class="registry-section"><h2>Register plot</h2><form id="plot-form" class="form-grid">${field('Facility','plot-facility',`<select id="plot-facility" name="facility_id" required><option value="">Optional</option>${options(boot.facilities,'id','name')}</select>`)}${field('Plot code','plot-code',`<input id="plot-code" name="code" required>`)}${field('Plot role','plot-role',`<select id="plot-role" name="role"><option value="unspecified">Unverified</option><option value="control">Control</option><option value="experimental">Experimental</option></select>`)}<div class="span-two"><label for="plot-notes">Layout and evidence</label><textarea id="plot-notes" name="notes"></textarea></div><button class="span-two">Save plot</button></form>
 <h3>Plots</h3>${table(['Code','Facility ID','Category'],boot.plots.map(r=>[h(r.code),r.facility_id,h({control:'Control',experimental:'Experimental',unspecified:'Unverified'}[r.role])]))}</section></div>`;
}
async function imports(){
 content.innerHTML=`<h1>Import data</h1><p class="lede">Import data using format-specific mapping and content-hash duplicate checks.</p>
 <div class="split"><section><form id="import-form"><label for="import-file">CSV file, up to 25 MB</label><input id="import-file" name="file" type="file" accept=".csv" required><div class="toolbar">${field('CSV Data group','import-group',`<select id="import-group" name="group"><option value="">Use group_name in standard CSV</option>${Object.entries(groups).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>`)}${field('Year for undated plant lists','import-year',`<input id="import-year" name="year" type="number" min="1900" max="2100" placeholder="Verified year">`)}</div><button id="import-submit">Validate and import</button></form><div id="import-result" role="status"></div></section>
 <section><h2>Supported data structures</h2><p>Plant and arthropod headers are mapped by their explicit names. Original rows and their positions are retained.</p><details><summary>Standard CSV schema</summary><pre>group_name,taxon_label,scientific_name,korean_name,survey_year,survey_month,survey_date,measurement_type,value,unit,raw_value</pre><p>group_name: plants / arthropods<br>measurement_type: presence_label / individual_count<br>Unit: count for individuals. Leave unverified months and days blank.</p></details></section></div>
 <h2>Data source</h2>${table(['ID','Data source name','Format','Original file hash'],boot.sources.map(r=>[r.id,h(r.name),h(r.encoding),`<details><summary>SHA-256 Check</summary><pre>${h(r.sha256)}</pre></details>`]))}`;
}
function makeSchema(nodes){
 const tables=nodes.filter(n=>n.type==='table'),order=['source_file','raw_row','import_file','taxon','observation','unresolved_cell','facility','plot','survey_event','sample','observation_context','quality_issue','revision_history','weather_station','weather_daily','observation_weather','weather_api_source','weather_api_response'];
 tables.sort((a,b)=>order.indexOf(a.name)-order.indexOf(b.name));let positions={},height=70;
 let rowY=40; for(let base=0;base<tables.length;base+=3){const rowNodes=tables.slice(base,base+3);let rowHeight=0;rowNodes.forEach((n,j)=>{const boxHeight=75+n.columns.length*21;positions[n.name]={x:30+j*470,y:rowY,w:420,h:boxHeight};rowHeight=Math.max(rowHeight,boxHeight);});rowY+=rowHeight+70;}height=rowY;
 let links='';for(const n of tables){const a=positions[n.name];for(const f of n.foreign_keys){const b=positions[f.table];if(!b)continue;links+=`<path d="M${a.x+a.w/2},${a.y}L${a.x+a.w/2},${a.y-18}L${b.x+b.w/2},${b.y+b.h+18}L${b.x+b.w/2},${b.y+b.h}" fill="none" stroke="#a2b7a8" stroke-width="1.5" marker-end="url(#arrow)"/>`;}}
 const boxes=tables.map(n=>{let p=positions[n.name];return `<g><rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" fill="white" stroke="#1d2b22"/><rect x="${p.x}" y="${p.y}" width="${p.w}" height="42" fill="#e9f2ec" stroke="#1d2b22"/><text x="${p.x+12}" y="${p.y+28}" font-size="19" font-weight="600">${h(n.name)}</text>${n.columns.map((c,i)=>`<text x="${p.x+12}" y="${p.y+67+i*21}" font-size="15">${c.pk?'PK ':''}${n.foreign_keys.some(f=>f.from===c.name)?'FK ':''}${h(c.name)} ${h(c.type)}</text>`).join('')}</g>`;}).join('');
 return `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="${height}" viewBox="0 0 1440 ${height}" role="img" aria-label="Implemented SQLite tables and foreign keys" font-family="sans-serif" fill="#1d2b22"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="#a2b7a8"/></marker></defs><rect width="1440" height="${height}" fill="white"/>${links}${boxes}</svg>`;
}
async function schema(){
 const nodes=await api('schema');schemaSVG=makeSchema(nodes);
 content.innerHTML=`<h1>Database schema</h1><p class="lede">Current database: ${nodes.filter(n=>n.type==='table').length} tables and ${nodes.filter(n=>n.type==='view').length} SQL views. PK: primary key; FK: declared foreign key.</p><div class="actions"><button id="download-schema">Save schema SVG</button><a class="download secondary" href="/api/backup">Download DB backup</a></div><h2>Tables and foreign keys</h2><div class="schema-view" tabindex="0">${schemaSVG}</div><h2>Fields and SQL definitions</h2>${nodes.map(n=>`<details class="schema-table"><summary>${h(n.name)} · ${n.type==='view'?'view':'Table'} · ${n.columns.length} fields</summary>${table(['Field','Type','Key','Required'],n.columns.map(c=>[h(c.name),h(c.type),c.pk?'PK':n.foreign_keys.filter(f=>f.from===c.name).map(f=>'FK '+h(f.table)+'.'+h(f.to)).join(', '),c.notnull?'Yes':'Optional']))}<pre>${h(n.sql)}</pre></details>`).join('')}`;
}
async function history(){const data=await api('history');content.innerHTML=`<h1>Revision history</h1><p class="lede">The 100 most recent revisions include previous/new values and evidence. Timestamps use UTC.</p>${table(['Time UTC','Target','Item','Evidence','Changed values'],data.map(r=>[h(r.changed_at),h(r.entity_type)+' '+r.entity_id,h(r.field_name),h(r.reason),`<details><summary>Before and after</summary><pre>${h(JSON.stringify({before:JSON.parse(r.old_json),after:JSON.parse(r.new_json)},null,2))}</pre></details>`]))}`;}
document.addEventListener('click',async event=>{
 const b=event.target.closest('button');if(!b)return;
 try{
  if(b.dataset.tab){state.page=1;await show(b.dataset.tab);return;}
  if(b.dataset.record){await openRecord(b.dataset.record);return;}
  if(b.id==='close-dialog'){dialog.close();return;}
  if(b.id==='reset-filters'){state.filters={};state.page=1;await show();}
  if(b.id==='prev-records'||b.id==='next-records'){state.page+=b.id==='prev-records'?-1:1;await show();}
  if(b.id==='prev-issues'||b.id==='next-issues'){state.issuePage+=b.id==='prev-issues'?-1:1;await show();}
  if(b.id==='prev-weather'||b.id==='next-weather'){state.weatherPage+=b.id==='prev-weather'?-1:1;weatherTable();}
  if(b.dataset.unresolved){const rows=await api('unresolved?source='+b.dataset.unresolved);document.querySelector('#unresolved-view').innerHTML='<h2>Unresolved cells (first 500)</h2>'+table(['Row','Column','Original text','Reason'],rows.map(r=>[r.row_number,r.column_number,h(r.raw_value),h(r.reason)]));}
  if(b.id==='download-schema'){const url=URL.createObjectURL(new Blob([schemaSVG],{type:'image/svg+xml'})),a=document.createElement('a');a.href=url;a.download='lmo_database_schema.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 }catch(error){fail(error,dialog.open);}
});
document.addEventListener('change',async event=>{
 try{
  if(event.target.id==='issue-status'){state.issueStatus=event.target.value;state.issuePage=1;await show();}
  if(event.target.id.startsWith('weather-')){if(event.target.id==='weather-station')state.station=event.target.value;if(event.target.id==='weather-year')state.weatherYear=Number(event.target.value);if(event.target.id==='weather-metric')state.metric=event.target.value;state.weatherPage=1;await show();}
  if(event.target.id==='context-facility'){document.querySelector('#context-plot').innerHTML='<option value="">Unspecified</option>'+options(boot.plots.filter(p=>String(p.facility_id)===event.target.value),'id','code');}
 }catch(error){fail(error);}
});
document.addEventListener('submit',async event=>{
 const form=event.target;if(!form.matches('form'))return;event.preventDefault();const submit=form.querySelector('button[type="submit"],button:not([type])');if(submit)submit.disabled=true;
 try{
  let data=formData(form);
  if(form.id==='filters'){state.filters=Object.fromEntries(Object.entries(data).filter(([,v])=>v));state.page=1;await show();}
  else if(form.id==='context-form'){let r=await api('context',{...data,observation_id:record.id});toast(`${count(r.updated)} records linked to survey information.`);await openRecord(record.id);}
  else if(form.id==='taxon-form'){await api('taxon',{...data,id:record.taxon_id});toast('Taxon names and evidence saved.');await openRecord(record.id);}
  else if(form.matches('.review-form')){await api('review',{...data,id:form.dataset.id});toast('Review saved.');await show();}
  else if(form.id==='facility-form'||form.id==='plot-form'){await api(form.id==='facility-form'?'facility':'plot',data);boot=await api('bootstrap');toast('Registered.');await show();}
  else if(form.id==='import-form'){
   const file=document.querySelector('#import-file').files[0];if(!file)throw new Error('Select a file.');if(file.size>25*1024*1024)throw new Error('File size must be 25 MB or smaller.');
   document.querySelector('#import-result').textContent='Checking source structure and values.';
   const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Unable to read the file.'));reader.readAsDataURL(file);});
   let r=await api('import',{filename:file.name,content:encoded,group:data.group,year:data.year});boot=await api('bootstrap');await show();document.querySelector('#import-result').textContent=r.message;toast(r.message);
  }
 }catch(error){fail(error,dialog.open);if(form.id==='import-form')document.querySelector('#import-result').textContent='Import failed. Review the error message.';}
 finally{if(submit)submit.disabled=false;}
});
const tabs=['overview','observations','quality','weather','experiments','aerial','registry','import','schema','history'];
api('bootstrap').then(data=>{boot=data;const t=location.hash.slice(1);show(tabs.includes(t)?t:'overview');}).catch(error=>fail(error));

async function experiments(){
 const data=await api('experiments');
 content.innerHTML=`<h1>Experiment designs</h1><p class="lede">${data.experiments.length} experiments and surveys defined by factors, levels, replication and measurement items. A measurement slot is one design unit paired with one item.</p>
 ${table(['ID','Experiment','Start','Setting','Unit sets','Design units','Items','Slots','Entered',''],data.experiments.map(e=>[h(e.id),h(e.title),h(e.start),h(e.setting),count(e.unit_sets),count(e.units),count(e.items),count(e.slots),count(e.measured),`<button class="secondary" data-experiment="${h(e.id)}">Open</button>`]))}
 <div id="experiment-detail"></div>
 <h2>Measurement labels shared across experiments</h2>${table(['Label','Experiments','IDs'],data.shared_labels.map(r=>[h(r.label),count(r.experiments),h(r.ids.split(',').join(', '))]))}`;
 content.querySelectorAll('[data-experiment]').forEach(b=>b.addEventListener('click',()=>openExperiment(b.dataset.experiment)));
}
async function openExperiment(id){
 const e=await api('experiment?id='+encodeURIComponent(id)),target=document.querySelector('#experiment-detail');
 target.innerHTML=`<h2>${h(e.id)} · ${h(e.title)}</h2><p>${h(e.start)} · ${h(e.setting)}</p>${e.unit_sets.map(s=>`<h3>${h(s.name)}</h3>${facts([['Unit',h(s.unit_label)],['Replication',s.replicate_n?h(s.replicate_n+' × '+s.replicate_label):'Not stated'],['Design units',count(s.units)],['Measurement slots',count(s.slots)],['Note',h(s.note||'—')]])}
 ${table(['Factor','Levels'],Object.entries(s.factors).map(([k,v])=>[h(k),h(v.join(', '))]))}${table(['Measurement item'],s.items.map(x=>[h(x)]))}`).join('')}`;
 target.scrollIntoView({block:'start',behavior:'smooth'});
}
async function aerial(){
 const data=await api('aerial'),labels=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
 content.innerHTML=`<h1>Aerial imagery inventory</h1><p class="lede">Monthly imagery coverage, 2019–2026. Production entries and linked original files have separate counts.</p>
 ${table(['Year','Managed months','Reported monthly products','Planned months','Linked files'],data.inventory.map(r=>[h(r.year),count(r.managed_months),count(r.reported_products),count(r.planned_months),count(r.linked_files)]))}
 <h2>Monthly production coverage</h2>${table(['Year',...labels],data.inventory.map(r=>[h(r.year),...data.months.filter(m=>m.year===r.year).map(m=>m.status==='planned'?'<span class="muted">Planned</span>':'Reported 1')]))}
 <p class="muted">Inventory cutoff: ${h(data.cutoff)}. Original file identifiers, capture dates and product metadata can be attached to each month.</p>`;
}
