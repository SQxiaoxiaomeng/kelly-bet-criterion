import { useMemo, useRef, useState, type PointerEvent } from "react";

import type { DailyBar } from "../api/data";

export function CandlestickChart({
  bars,
  onOlder,
  onNewer,
  canShowNewer,
  canShowOlder,
  tradeMarkers = [],
  showNavigation = true,
}: {
  bars: DailyBar[];
  onOlder: () => void;
  onNewer: () => void;
  canShowNewer: boolean;
  canShowOlder: boolean;
  tradeMarkers?: Array<{ trade_date: string; side: string; price: string; quantity: number; fee: string }>;
  showNavigation?: boolean;
}) {
  const [visibleCount, setVisibleCount] = useState(240);
  const [hoveredIndex, setHoveredIndex] = useState<number>();
  const [dragStartIndex, setDragStartIndex] = useState<number>();
  const [dragEndIndex, setDragEndIndex] = useState<number>();
  const [zoomRange, setZoomRange] = useState<{ start: number; end: number }>();
  const panDelayTimer = useRef<number | undefined>(undefined);
  const panTimer = useRef<number | undefined>(undefined);
  const visibleBars = useMemo(() => {
    if (zoomRange) return bars.slice(zoomRange.start, zoomRange.end + 1);
    return bars.slice(-visibleCount);
  }, [bars, visibleCount, zoomRange]);
  if (bars.length === 0) return <p>暂无可展示的日线数据。</p>;
  const width = 900;
  const height = 420;
  const padding = { top: 24, right: 68, bottom: 48, left: 18 };
  const values = visibleBars.flatMap((bar) => [Number(bar.high), Number(bar.low)]);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const scaleY = (value: number) => {
    const range = maximum - minimum || 1;
    return padding.top + ((maximum - value) / range) * (height - padding.top - padding.bottom);
  };
  const step = (width - padding.left - padding.right) / visibleBars.length;
  const bodyWidth = Math.max(1, step * 0.65);
  const priceTicks = Array.from({ length: 5 }, (_, index) => maximum - ((maximum - minimum) * index) / 4);
  const dateTickIndexes = Array.from(
    new Set([0, Math.floor(visibleBars.length / 4), Math.floor(visibleBars.length / 2), Math.floor(visibleBars.length * 0.75), visibleBars.length - 1]),
  );
  const hoveredBar = hoveredIndex === undefined ? undefined : visibleBars[hoveredIndex];
  const hoveredTrades = hoveredBar
    ? tradeMarkers.filter((trade) => trade.trade_date === hoveredBar.trade_date)
    : [];
  const hoveredFullIndex = hoveredBar ? bars.indexOf(hoveredBar) : -1;
  const previousClose = hoveredFullIndex > 0 ? Number(bars[hoveredFullIndex - 1].close) : undefined;
  const changePercent = hoveredBar && previousClose
    ? ((Number(hoveredBar.close) - previousClose) / previousClose) * 100
    : undefined;

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    const index = pointerToIndex(event);
    setHoveredIndex(index);
    if (dragStartIndex !== undefined) setDragEndIndex(index);
  }

  function pointerToIndex(event: PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const index = Math.floor((x - padding.left) / step);
    return index >= 0 && index < visibleBars.length ? index : undefined;
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    const index = pointerToIndex(event);
    if (index === undefined) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStartIndex(index);
    setDragEndIndex(index);
  }

  function handlePointerUp(event: PointerEvent<SVGSVGElement>) {
    const endIndex = pointerToIndex(event);
    if (dragStartIndex !== undefined && endIndex !== undefined && endIndex !== dragStartIndex) {
      const startBar = visibleBars[Math.min(dragStartIndex, endIndex)];
      const endBar = visibleBars[Math.max(dragStartIndex, endIndex)];
      setZoomRange({ start: bars.indexOf(startBar), end: bars.indexOf(endBar) });
    }
    setDragStartIndex(undefined);
    setDragEndIndex(undefined);
  }

  function startPanning(event: PointerEvent<HTMLButtonElement>, action: () => void) {
    if (event.button !== 0) return;
    event.preventDefault();
    action();
    panDelayTimer.current = window.setTimeout(() => {
      panTimer.current = window.setInterval(action, 180);
    }, 500);
  }

  function stopPanning() {
    if (panDelayTimer.current !== undefined) window.clearTimeout(panDelayTimer.current);
    if (panTimer.current !== undefined) window.clearInterval(panTimer.current);
    panDelayTimer.current = undefined;
    panTimer.current = undefined;
  }

  function adjustVisibleRange(change: number) {
    if (!zoomRange) {
      setVisibleCount((count) => Math.max(20, Math.min(bars.length, count + change)));
      return;
    }

    const currentCount = zoomRange.end - zoomRange.start + 1;
    const targetCount = Math.max(20, Math.min(bars.length, currentCount + change));
    if (targetCount === currentCount) return;

    const center = (zoomRange.start + zoomRange.end) / 2;
    let start = Math.round(center - (targetCount - 1) / 2);
    start = Math.max(0, Math.min(bars.length - targetCount, start));
    setZoomRange({ start, end: start + targetCount - 1 });
  }

  const selectionStart = dragStartIndex === undefined || dragEndIndex === undefined
    ? undefined
    : Math.min(dragStartIndex, dragEndIndex);
  const selectionEnd = dragStartIndex === undefined || dragEndIndex === undefined
    ? undefined
    : Math.max(dragStartIndex, dragEndIndex);

  return (
    <div className="chart-wrapper">
      <div className="chart-controls">
        {showNavigation ? <button type="button" onPointerDown={(event) => startPanning(event, onOlder)} onPointerUp={stopPanning} onPointerLeave={stopPanning} onPointerCancel={stopPanning} disabled={!canShowOlder}>←</button> : null}
        <button type="button" onClick={() => adjustVisibleRange(-30)}>缩短区间</button>
        <span>显示最近 {visibleBars.length} / {bars.length} 根日线</span>
        <button type="button" onClick={() => adjustVisibleRange(30)}>拉长区间</button>
        {showNavigation ? <button type="button" onPointerDown={(event) => startPanning(event, onNewer)} onPointerUp={stopPanning} onPointerLeave={stopPanning} onPointerCancel={stopPanning} disabled={!canShowNewer}>→</button> : null}
      </div>
      <svg className="candlestick-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="带坐标轴的日K线图" onPointerMove={handlePointerMove} onPointerDown={handlePointerDown} onPointerUp={handlePointerUp} onPointerLeave={() => { setHoveredIndex(undefined); if (dragStartIndex !== undefined) { setDragStartIndex(undefined); setDragEndIndex(undefined); } }}>
        {priceTicks.map((price) => {
          const y = scaleY(price);
          return <g key={price}><line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="chart-grid" /><text x={width - padding.right + 8} y={y + 4} className="chart-label">{price.toFixed(2)}</text></g>;
        })}
        <line x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} className="chart-axis" />
        {visibleBars.map((bar, index) => {
          const x = padding.left + index * step + step / 2;
          const open = Number(bar.open);
          const close = Number(bar.close);
          const color = close >= open ? "#ef5350" : "#26a69a";
          const top = scaleY(Math.max(open, close));
          const bodyHeight = Math.max(1, Math.abs(scaleY(open) - scaleY(close)));
          return <g key={bar.trade_date}><line x1={x} x2={x} y1={scaleY(Number(bar.high))} y2={scaleY(Number(bar.low))} stroke={color} /><rect x={x - bodyWidth / 2} y={top} width={bodyWidth} height={bodyHeight} fill={color} /></g>;
        })}
        {visibleBars.flatMap((bar, index) => tradeMarkers.filter((trade) => trade.trade_date === bar.trade_date).map((trade) => {
          const x = padding.left + index * step + step / 2;
          const isBuy = trade.side === "BUY";
          const y = isBuy
            ? Math.max(padding.top + 12, scaleY(Number(bar.low)) - 12)
            : Math.min(height - padding.bottom - 12, scaleY(Number(bar.high)) + 12);
          const color = isBuy ? "#7bb8ff" : "#f6c453";
          const markerRadius = showNavigation
            ? Math.min(6, bodyWidth / 2)
            : Math.min(8, Math.max(4, bodyWidth * 0.8));
          return <g key={`${trade.trade_date}-${trade.side}-${trade.price}`} className="trade-marker"><circle cx={x} cy={y} r={markerRadius} fill={color} /><text x={x} y={y + markerRadius * 0.35} textAnchor="middle" className="trade-marker-label" style={{ fontSize: `${Math.max(3, markerRadius * 1.2)}px` }}>{isBuy ? "B" : "S"}</text></g>;
        }))}
        {selectionStart !== undefined && selectionEnd !== undefined ? <rect x={padding.left + selectionStart * step} y={padding.top} width={(selectionEnd - selectionStart + 1) * step} height={height - padding.top - padding.bottom} className="chart-selection" /> : null}
        {hoveredBar && hoveredIndex !== undefined ? <line x1={padding.left + hoveredIndex * step + step / 2} x2={padding.left + hoveredIndex * step + step / 2} y1={padding.top} y2={height - padding.bottom} className="chart-crosshair" /> : null}
        {dateTickIndexes.map((index) => { const x = padding.left + index * step + step / 2; return <text key={visibleBars[index].trade_date} x={x} y={height - 18} textAnchor="middle" className="chart-label">{visibleBars[index].trade_date}</text>; })}
      </svg>
      {hoveredBar ? <div className="chart-tooltip"><strong>{hoveredBar.trade_date}</strong><span>开 {hoveredBar.open}</span><span>高 {hoveredBar.high}</span><span>低 {hoveredBar.low}</span><span>收 {hoveredBar.close}</span><span className={changePercent === undefined ? "" : changePercent >= 0 ? "price-up" : "price-down"}>涨跌幅 {changePercent === undefined ? "-" : `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`}</span>{hoveredTrades.map((trade) => <span key={`${trade.trade_date}-${trade.side}-${trade.price}`} className={trade.side === "BUY" ? "price-up" : "price-down"}>{trade.side === "BUY" ? "买入" : "卖出"} {trade.price} × {trade.quantity}</span>)}</div> : null}
    </div>
  );
}
