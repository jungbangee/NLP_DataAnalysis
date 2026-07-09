const radarCtx = document.getElementById('radarChart').getContext('2d');
const radar = new Chart(radarCtx, {
  type: 'radar',
  data: {
    labels: ['언어표현','도입·구조','개념명확','예시·실습','상호작용'],
    datasets:[{label:'점수',data:[3.5,3.0,3.2,3.8,4.1],backgroundColor:'rgba(37,99,235,0.2)',borderColor:'rgba(37,99,235,0.8)'}]
  },
  options:{scales:{r:{grid:{color:'#102033'},angleLines:{color:'#102033'},ticks:{color:'#9aa6b3',beginAtZero:true,min:0,max:5,stepSize:1}}},plugins:{legend:{display:false}}}
});

const barCtx = document.getElementById('barChart').getContext('2d');
const bar = new Chart(barCtx,{
  type:'bar',
  data:{labels:['언어표현','도입·구조','개념명확','예시·실습','상호작용'],datasets:[{data:[3.5,3.0,3.2,3.8,4.1],backgroundColor:['#2563eb','#2563eb','#2563eb','#10b981','#2563eb']}]},
  options:{indexAxis:'y',scales:{x:{beginAtZero:true,max:5,ticks:{color:'#9ca3af'}},y:{ticks:{color:'#e6eef6'}}},plugins:{legend:{display:false}}}
});

const lineCtx = document.getElementById('lineChart').getContext('2d');
const line = new Chart(lineCtx,{type:'line',data:{labels:['02-02','02-06','02-10','02-13','02-17','02-21','02-27'],datasets:[{label:'점수',data:[68,70,72,71,73,74,74],borderColor:'#60a5fa',backgroundColor:'rgba(96,165,250,0.15)',fill:true}]},options:{scales:{y:{beginAtZero:true,ticks:{color:'#9ca3af'}} ,x:{ticks:{color:'#cbd5e1'}}},plugins:{legend:{display:false}}}});
