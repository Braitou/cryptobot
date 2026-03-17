const categoryStyles = {
  pattern: { color: 'text-blue-400', bg: 'bg-blue-500/20', border: 'border-blue-500/30' },
  mistake: { color: 'text-red-400', bg: 'bg-red-500/20', border: 'border-red-500/30' },
  insight: { color: 'text-purple-400', bg: 'bg-purple-500/20', border: 'border-purple-500/30' },
  rule: { color: 'text-emerald-400', bg: 'bg-emerald-500/20', border: 'border-emerald-500/30' },
}

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-slate-500 font-mono">{value.toFixed(1)}</span>
    </div>
  )
}

export default function MemoryView({ memory }) {
  const entries = (memory?.entries || [])
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
    .slice(0, 10)

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800">
        <h3 className="text-sm font-medium text-slate-300">
          Mémoire <span className="text-slate-500">({entries.length} top leçons)</span>
        </h3>
      </div>
      <div className="divide-y divide-slate-800/50">
        {entries.length === 0 ? (
          <div className="px-4 py-3 text-xs text-slate-500 italic">Aucune leçon</div>
        ) : (
          entries.map((e) => {
            const style = categoryStyles[e.category] || categoryStyles.insight
            return (
              <div key={e.id} className="px-4 py-2.5 flex items-start gap-2">
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 mt-0.5 ${style.bg} ${style.color} ${style.border}`}>
                  {e.category}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-300 leading-relaxed">{e.content}</p>
                  <ConfidenceBar value={e.confidence || 0} />
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
