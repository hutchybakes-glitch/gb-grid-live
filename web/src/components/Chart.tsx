// Thin ECharts wrapper: registers only the pieces we use (smaller bundle),
// follows the site theme and respects reduced-motion preferences.
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useTheme } from '../lib/theme'

echarts.use([
  BarChart, HeatmapChart, LineChart, PieChart, ScatterChart,
  AriaComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent,
  TooltipComponent, VisualMapComponent, CanvasRenderer,
])

export type ChartOption = echarts.EChartsCoreOption

interface Props {
  option: ChartOption
  /** Text alternative describing what the chart shows. */
  label: string
  className?: string
}

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

export default function Chart({ option, label, className = 'chart' }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const theme = useTheme()

  useEffect(() => {
    if (!el.current) return
    chart.current = echarts.init(el.current, undefined, { renderer: 'canvas' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(el.current)
    return () => {
      ro.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    const css = getComputedStyle(document.documentElement)
    const text = css.getPropertyValue('--text').trim()
    const muted = css.getPropertyValue('--text-muted').trim()
    const surface = css.getPropertyValue('--surface').trim()
    chart.current?.setOption(
      {
        animation: !reducedMotion(),
        animationDuration: 300,
        textStyle: { fontFamily: 'Inter, system-ui, sans-serif', color: muted },
        aria: { enabled: true, label: { description: label } },
        tooltip: {
          backgroundColor: surface,
          borderColor: muted,
          textStyle: { color: text },
        },
        ...option,
      },
      { notMerge: true },
    )
  }, [option, label, theme])

  return <div ref={el} className={className} role="img" aria-label={label} />
}

/** Shared axis styling so every chart looks the same. */
export function axisStyle() {
  const css = getComputedStyle(document.documentElement)
  const muted = css.getPropertyValue('--text-muted').trim()
  const grid = css.getPropertyValue('--grid').trim()
  return {
    axisLine: { lineStyle: { color: grid } },
    axisTick: { show: false },
    axisLabel: { color: muted },
    splitLine: { lineStyle: { color: grid } },
    nameTextStyle: { color: muted },
  }
}
