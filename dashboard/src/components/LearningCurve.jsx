import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'

export default function LearningCurve({ data }) {
  if (!data || data.length < 2) return null

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <Line
          type="monotone"
          dataKey="winRate"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
        />
        <Tooltip
          contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', fontSize: '11px' }}
          labelFormatter={(v) => `Tranche ${v}`}
          formatter={(v) => [`${v}%`, 'Win rate']}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
