/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Home } from './pages/Home';
import { DealDetail } from './pages/DealDetail';
import { Subscribe } from './pages/Subscribe';
import { Navbar } from './components/Navbar';
import { Zap, X, ArrowRightLeft } from 'lucide-react';
import { ComparisonProvider, useComparison } from './lib/ComparisonContext';
import { useState } from 'react';
import { cn } from './lib/utils';

function ComparisonTray() {
  const { compareList, removeFromCompare, clearCompare } = useComparison();
  const [isOpen, setIsOpen] = useState(false);

  if (compareList.length === 0) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-slate-200 shadow-[0_-10px_30px_rgba(0,0,0,0.1)] p-4 animate-in slide-in-from-bottom duration-300">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-6 overflow-x-auto pb-2">
          <div className="flex flex-col">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-widest leading-none mb-1">Comparing</span>
            <span className="text-lg font-bold text-slate-900">{compareList[0].productType}s</span>
          </div>
          <div className="flex items-center gap-3">
            {compareList.map((item) => (
              <div key={item.id} className="flex items-center gap-2 bg-slate-100 p-2 rounded-xl group relative">
                <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center p-1 border border-slate-200">
                  {item.imageUrl ? <img src={item.imageUrl} alt="" className="max-h-full object-contain" /> : <Zap className="w-4 h-4 text-slate-300" />}
                </div>
                <div className="flex flex-col max-w-[120px]">
                  <span className="text-[10px] font-bold text-slate-900 line-clamp-1">{item.productName}</span>
                  <span className="text-[10px] text-blue-600 font-bold">AED {item.price.toLocaleString()}</span>
                </div>
                <button 
                  onClick={() => removeFromCompare(item.id)}
                  className="bg-slate-900 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity absolute -top-2 -right-2"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
            {compareList.length < 3 && (
              <div className="w-10 h-10 border-2 border-dashed border-slate-200 rounded-xl flex items-center justify-center text-slate-300">
                +
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button onClick={clearCompare} className="text-slate-500 text-xs font-bold hover:text-slate-900 transition-colors uppercase tracking-widest">
            Clear
          </button>
          <button 
            onClick={() => setIsOpen(true)}
            disabled={compareList.length < 2}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-200 text-white px-8 py-3 rounded-xl text-sm font-bold flex items-center gap-2 transition-all shadow-lg shadow-blue-600/20"
          >
            <ArrowRightLeft className="w-4 h-4" />
            Compare Now
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="fixed inset-0 z-[60] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-6xl rounded-3xl overflow-hidden shadow-2xl animate-in zoom-in duration-300">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-xl font-bold text-slate-900">Side-by-Side Comparison</h2>
              <button onClick={() => setIsOpen(false)} className="p-2 hover:bg-slate-100 rounded-full transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-8 overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="py-4 w-1/4" />
                    {compareList.map(item => (
                      <th key={item.id} className="py-4 px-6 text-center">
                         <div className="h-32 mb-4 bg-slate-50 rounded-xl flex items-center justify-center p-4">
                           {item.imageUrl ? <img src={item.imageUrl} alt="" className="max-h-full object-contain" /> : <Zap className="w-8 h-8 text-slate-300" />}
                         </div>
                         <div className="text-sm font-bold text-slate-900 mb-1">{item.productName}</div>
                         <div className="text-lg font-bold text-blue-600">AED {item.price.toLocaleString()}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                   <tr className="border-b border-slate-50">
                    <td className="py-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Brand</td>
                    {compareList.map(item => <td key={item.id} className="py-4 px-6 text-center text-sm font-semibold">{item.specs?.brand || 'N/A'}</td>)}
                  </tr>
                  <tr className="border-b border-slate-50">
                    <td className="py-4 text-xs font-bold text-slate-400 uppercase tracking-widest">Retailer</td>
                    {compareList.map(item => <td key={item.id} className="py-4 px-6 text-center text-sm font-bold text-emerald-600">{item.store}</td>)}
                  </tr>
                  {/* Dynamic specs based on the first item's keys */}
                  {Object.keys(compareList[0].specs || {}).map(specKey => (
                    <tr key={specKey} className="border-b border-slate-50">
                      <td className="py-4 text-xs font-bold text-slate-400 uppercase tracking-widest capitalize">{specKey}</td>
                      {compareList.map(item => (
                        <td key={item.id} className="py-4 px-6 text-center text-sm font-medium text-slate-700">
                          {item.specs[specKey] || '-'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="p-6 bg-slate-50 flex justify-end">
              <button onClick={() => setIsOpen(false)} className="bg-slate-900 text-white px-8 py-3 rounded-xl text-sm font-bold tracking-widest uppercase">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <Router>
      <ComparisonProvider>
        <div className="min-h-screen bg-slate-50 text-slate-900 font-sans selection:bg-blue-600/20">
          <Navbar />
          <main className="max-w-7xl mx-auto">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/deal/:id" element={<DealDetail />} />
              <Route path="/subscribe" element={<Subscribe />} />
            </Routes>
          </main>
          
          <ComparisonTray />
          
          <footer className="border-t border-slate-200 py-12 mt-12 bg-white">
          <div className="max-w-7xl mx-auto px-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-4">
              <Zap className="w-5 h-5 text-blue-600 fill-current" />
              <span className="font-bold text-slate-900 tracking-tight">OASIS DEALS</span>
            </div>
            <p className="text-slate-500 text-xs uppercase tracking-widest">
              © 2026 UAE Gaming Deals. Premium Hardware Monitoring for the MEA Region.
            </p>
          </div>
        </footer>
      </div>
      </ComparisonProvider>
    </Router>
  );
}
