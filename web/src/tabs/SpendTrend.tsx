import { useEffect, useState } from "react";
import { getSessions } from "../api";
import CONFIG from "../config.json";
import { errorText } from "../errors";
import { locale, t } from "../i18n";
import { DaySpend, dailySpend, peakDay } from "../spend";
import { Sparkline } from "../Sparkline";
import { formatUsd } from "../utils";

const { days, sessionLimit, refreshSec } = CONFIG.spendTrend;

function weekday(ms: number): string {
  return new Intl.DateTimeFormat(locale(), { weekday: "short" }).format(ms);
}

/** Status card: spend per day over the configured number of days. */
export function SpendTrend() {
  const [series, setSeries] = useState<DaySpend[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await getSessions(sessionLimit);
        if (!cancelled) {
          setSeries(dailySpend(r.sessions, days));
          setErr(null);
        }
      } catch (e) {
        if (!cancelled) setErr(errorText(e));
      }
    };
    tick();
    const id = setInterval(tick, refreshSec * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!series) {
    return err ? <div className="spend-trend muted">{err}</div> : null;
  }

  const total = series.reduce((a, s) => a + s.usd, 0);
  const peak = peakDay(series);
  const values = series.map((s) => s.usd);

  return (
    <div className="spend-trend">
      <div className="spend-trend-head">
        <span className="name">{t("status.trend", { days })}</span>
        <span className="total">{formatUsd(total)}</span>
      </div>
      <Sparkline
        values={values}
        label={t("status.trendAria", { days, total: formatUsd(total) })}
      />
      <div className="spend-trend-axis" aria-hidden="true">
        <span>{weekday(series[0].day)}</span>
        <span>{t("status.window.today")}</span>
      </div>
      <div className="spend-trend-foot">
        {!peak
          ? t("status.trendEmpty", { days })
          : peak.index === series.length - 1
            ? t("status.trendPeakToday", { usd: formatUsd(peak.usd) })
            : t("status.trendPeak", { usd: formatUsd(peak.usd), day: weekday(series[peak.index].day) })}
      </div>
    </div>
  );
}
