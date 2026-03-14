const t=[],s=new Set,c=e=>{e.forEach(n=>s.add(n)),t.length=0,t.push(...Array.from(s))},a=async()=>{const e=await(await fetch("/frequencyList.json")).json();c(e)};export{t as a,a as f};
