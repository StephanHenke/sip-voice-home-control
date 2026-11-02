'use strict';
window.configForm = (() => {
  let documentData=null, changed=false;
  const root=()=>document.getElementById('settingsForm');
  const element=(tag,text,className)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;};
  const labels={callback:'Rückruf an gespeicherte Nummer',direct:'Direkt annehmen',state:'Gerätezustände / Werte',rollershutter_opening:'Rolladenposition / Bewegung',reject:'Anruf abweisen',answer_hangup:'Kurz annehmen und auflegen',none:'Keine Logs',console:'Konsole',file:'Datei',syslog:'Remote-Syslog'};
  const label=k=>documentData.labels[k]||k;
  function touch(){changed=true;document.getElementById('editor').dispatchEvent(new Event('input'));}
  function help(parent,key){if(documentData.help[key])parent.append(element('small',documentData.help[key],'field-help'));}
  function field(parent,obj,key,path){
    const value=obj[key],box=element('div',undefined,'form-field');
    const title=element('label',label(key));box.append(title);parent.append(box);
    if(Array.isArray(value)&&value.every(v=>typeof v==='string')){
      const input=element('textarea');input.rows=Math.max(2,Math.min(6,value.length));input.value=value.join('\n');
      title.append(input);if(key==='id')input.onchange=()=>render();
      input.oninput=()=>{obj[key]=input.value.split('\n').map(s=>s.trim()).filter(Boolean);touch();};
    }else if(value&&typeof value==='object'&&!Array.isArray(value)){
      if(key==='state_values'){
        for(const state of Object.keys(value)){
          const row=element('div',undefined,'mapping-row');box.append(row);field(row,value,state,path+'.'+state);
          const remove=element('button','Entfernen');remove.type='button';remove.onclick=()=>{delete value[state];touch();render();};row.append(remove);
        }
        const row=element('div',undefined,'row'),input=element('input'),add=element('button','Zustand hinzufügen');
        input.placeholder='z. B. opened';input.setAttribute('aria-label','Neuer Zustandsname');add.type='button';
        add.onclick=()=>{const name=input.value.trim();if(!/^[a-z][a-z0-9_]*$/.test(name)||['__proto__','constructor','prototype'].includes(name)||Object.hasOwn(value,name)){input.setCustomValidity('Eindeutigen Zustandsnamen eingeben (a–z, 0–9, _).');input.reportValidity();return;}value[name]=[];touch();render();};
        input.oninput=()=>input.setCustomValidity('');row.append(input,add);box.append(row);
      }else{for(const child of Object.keys(value))field(box,value,child,path+'.'+child);}
    }else{
      const options=key==='fixed_action'?['',...documentData.config.actions.map(a=>a.id).filter(Boolean)]:documentData.options[path]||documentData.options[key];
      const input=element(options?'select':'input');title.append(input);
      if(options){
        const choices=[...new Set([...options,...(typeof value==='string'&&!options.includes(value)?[value]:[])])];
        for(const option of choices){const el=element('option',option===''?'Normaler Sprachdialog':labels[option]||option);el.value=option;input.append(el);}input.value=value;
      }else if(typeof value==='boolean'){input.type='checkbox';input.checked=value;title.classList.add('check-label');}
      else if(typeof value==='number'){input.type='number';input.step='any';input.value=value;}
      else{input.type=['password','token'].includes(key)?'password':'text';input.value=value??'';input.autocomplete='off';if(input.type==='password'){input.autocomplete='new-password';input.placeholder='Neuen Wert eingeben';}}
      if(key==='id')input.onchange=()=>render();
      input.oninput=()=>{obj[key]=typeof value==='boolean'?input.checked:typeof value==='number'?(input.value===''?null:Number(input.value)):input.value;touch();};
      if(['password','token'].includes(key)&&typeof value==='string'&&value.startsWith('enc:v1:'))box.append(element('small','Verschlüsselt gespeichert. Zum Ändern den Feldinhalt ersetzen.','secret-state'));
    }
    help(box,key);
  }
  function render(){
    const node=root();node.replaceChildren();if(!documentData)return;
    for(const [key,value] of Object.entries(documentData.config)){
      if(!value||typeof value!=='object'){field(node,documentData.config,key,key);continue;}
      const group=element('details',undefined,'settings-group');group.open=['sip','openhab','callers','actions'].includes(key);
      group.append(element('summary',label(key)+(Array.isArray(value)?' ('+value.length+')':'')));help(group,key);node.append(group);
      if(['callers','actions'].includes(key)){
        value.forEach((item,i)=>{
          const card=element('details',undefined,'entry-card');card.open=key==='callers'?!item.name:!item.id;
          card.append(element('summary',(key==='callers'?(item.name||'Neuer Anrufer'):(item.id||'Neue Aktion'))+' · '+(i+1)));
          const fields=element('div',undefined,'form-grid');card.append(fields);
          for(const child of Object.keys(item))field(fields,item,child,key+'.'+i+'.'+child);
          const remove=element('button',key==='callers'?'Anrufer entfernen':'Aktion entfernen');remove.type='button';
          remove.onclick=()=>{if(confirm('Diesen Eintrag aus dem Entwurf entfernen?')){value.splice(i,1);touch();render();}};card.append(remove);group.append(card);
        });
        const add=element('button',key==='callers'?'+ Anrufer hinzufügen':'+ Aktion hinzufügen');add.type='button';
        add.onclick=()=>{value.push(structuredClone(documentData.templates[key]));touch();render();};group.append(add);
      }else{const grid=element('div',undefined,'form-grid');for(const child of Object.keys(value))field(grid,value,child,key+'.'+child);group.append(grid);}
    }
  }
  return {
    async load(text){documentData=await api('form',{yaml:text});changed=false;render();},
    async yaml(original){if(!changed)return original;return (await api('form/yaml',{config:documentData.config})).yaml;},
    clear(){documentData=null;changed=false;root().replaceChildren();},
    get changed(){return changed;}
  };
})();
