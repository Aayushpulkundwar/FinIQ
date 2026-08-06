import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import type { TopMover, TopMoversResponse } from '../../types';
import { Clock } from 'lucide-react';
import './MarketTicker.css';

export const MarketTicker: React.FC = () => {
  const [moversData, setMoversData] = useState<TopMoversResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isError, setIsError] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;

    const fetchMovers = async () => {
      try {
        const data = await api.getTopMovers();
        if (isMounted) {
          setMoversData(data);
          setIsError(false);
          setIsLoading(false);
        }
      } catch (err) {
        console.warn('Failed to fetch top movers ticker data:', err);
        if (isMounted) {
          setIsError(true);
          setIsLoading(false);
        }
      }
    };

    fetchMovers();
    const interval = setInterval(fetchMovers, 45000); // 45s polling

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const movers = moversData?.movers || [];
  const isMarketOpen = moversData?.market_open ?? true;

  // Duplicate array for smooth horizontal infinite scroll
  const displayMovers = [...movers, ...movers];

  return (
    <div className="market-ticker-strip">
      {!isMarketOpen && (
        <div className="market-ticker-closed-badge">
          <Clock size={12} />
          <span>Market Closed</span>
        </div>
      )}

      {isLoading && (
        <div className="market-ticker-skeleton">
          <div className="market-ticker-skeleton-item" />
          <div className="market-ticker-skeleton-item" />
          <div className="market-ticker-skeleton-item" />
          <div className="market-ticker-skeleton-item" />
          <div className="market-ticker-skeleton-item" />
        </div>
      )}

      {!isLoading && isError && movers.length === 0 && (
        <div className="market-ticker-error">
          Market data unavailable
        </div>
      )}

      {!isLoading && movers.length > 0 && (
        <div className="market-ticker-container">
          <div className="market-ticker-track">
            {displayMovers.map((mover, idx) => {
              const isGain = mover.pct_change >= 0;
              const sign = isGain ? '+' : '';
              const changeClass = isGain ? 'up' : 'down';

              return (
                <div key={`${mover.symbol}-${idx}`} className="market-ticker-item">
                  <span className="market-ticker-symbol">{mover.symbol}</span>
                  <span className="market-ticker-price">₹{mover.price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <span className={`market-ticker-change ${changeClass}`}>
                    {sign}{mover.change.toFixed(2)} ({sign}{mover.pct_change.toFixed(2)}%)
                  </span>
                  <span className="market-ticker-divider">|</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
