import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Deal } from '../types';

interface ComparisonContextType {
  compareList: Deal[];
  addToCompare: (deal: Deal) => void;
  removeFromCompare: (id: string) => void;
  clearCompare: () => void;
  isComparing: (id: string) => boolean;
}

const ComparisonContext = createContext<ComparisonContextType | undefined>(undefined);

export function ComparisonProvider({ children }: { children: ReactNode }) {
  const [compareList, setCompareList] = useState<Deal[]>([]);

  const addToCompare = (deal: Deal) => {
    setCompareList(prev => {
      // Restriction: Only same category members
      if (prev.length > 0 && prev[0].productType !== deal.productType) {
        alert("You can only compare products of the same category.");
        return prev;
      }
      if (prev.length >= 3) {
        alert("You can compare up to 3 products at a time.");
        return prev;
      }
      if (prev.some(item => item.id === deal.id)) return prev;
      return [...prev, deal];
    });
  };

  const removeFromCompare = (id: string) => {
    setCompareList(prev => prev.filter(item => item.id !== id));
  };

  const clearCompare = () => setCompareList([]);

  const isComparing = (id: string) => compareList.some(item => item.id === id);

  return (
    <ComparisonContext.Provider value={{ compareList, addToCompare, removeFromCompare, clearCompare, isComparing }}>
      {children}
    </ComparisonContext.Provider>
  );
}

export function useComparison() {
  const context = useContext(ComparisonContext);
  if (!context) throw new Error('useComparison must be used within a ComparisonProvider');
  return context;
}
