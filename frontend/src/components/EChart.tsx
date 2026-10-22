import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import type { ECharts, EChartsCoreOption } from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

/** Cores do tema escuro, compartilhadas pelos gráficos próprios. */
export const CHART = {
  text: "#a1a1aa",
  axis: "#52525b",
  grid: "#27272a",
  palette: ["#34d399", "#60a5fa", "#fbbf24", "#f472b6"],
};

export default function EChart({ option, height = 260 }: { option: EChartsCoreOption; height?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ECharts | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const c = echarts.init(el);
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize()); // também cobre a aba que estava oculta
    ro.observe(el);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, true);
  }, [option]);

  return <div ref={host} style={{ height, width: "100%" }} />;
}
