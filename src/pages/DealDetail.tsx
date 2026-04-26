import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { gamingDealsService } from '../lib/dealsService';
import { Deal } from '../types';
import { ArrowLeft, ExternalLink, Calendar, ShieldCheck, Truck, Store, ArrowRightLeft } from 'lucide-react';
import { useComparison } from '../lib/ComparisonContext';
import { cn } from '../lib/utils';

export function DealDetail() {
  const { id } = useParams();
  const [deal, setDeal] = useState<Deal | null>(null);
  const [loading, setLoading] = useState(true);
  const { addToCompare, isComparing, removeFromCompare } = useComparison();

  useEffect(() => {
    if (id) {
      gamingDealsService.getDeal(id).then(data => {
        setDeal(data);
        setLoading(false);
      });
    }
  }, [id]);

  if (loading) return <div className="p-20 text-center text-slate-500">Loading deal details...</div>;
  if (!deal) return <div className="p-20 text-center text-red-500">Deal not found.</div>;

  return (
    <div className="max-w-6xl mx-auto px-4 py-12">
      <Link to="/" className="inline-flex items-center gap-2 text-slate-500 hover:text-blue-600 text-sm mb-8 font-medium transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to all deals
      </Link>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 bg-white p-8 md:p-12 rounded-3xl border border-slate-200">
        {/* Gallery */}
        <div className="space-y-6">
          <div className="bg-slate-50 aspect-square rounded-2xl flex items-center justify-center p-12 border border-slate-100">
            {deal.imageUrl ? (
              <img src={deal.imageUrl} alt={deal.productName} className="max-w-full max-h-full object-contain" referrerPolicy="no-referrer" />
            ) : (
              <div className="text-slate-200 text-9xl font-bold">Hardware</div>
            )}
          </div>
        </div>

        {/* Info */}
        <div className="flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <span className="bg-blue-600 text-white text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded">
              {deal.productType}
            </span>
            <span className="text-slate-400 text-xs font-semibold uppercase tracking-widest">
              Verified Deal
            </span>
          </div>

          <h1 className="text-3xl font-bold text-slate-900 leading-tight mb-4">
            {deal.productName}
          </h1>

          <div className="flex items-center gap-4 mb-8">
            <div className="flex flex-col">
              <span className="text-3xl font-bold text-slate-900">AED {deal.price.toLocaleString()}</span>
              {deal.originalPrice > deal.price && (
                <span className="text-slate-400 line-through text-lg">AED {deal.originalPrice.toLocaleString()}</span>
              )}
            </div>
            {deal.discountPercentage > 0 && (
              <div className="bg-emerald-500 text-white font-bold px-3 py-1 rounded-lg text-sm">
                -{Math.round(deal.discountPercentage)}% Saving
              </div>
            )}
          </div>

          <div className="flex flex-col sm:flex-row gap-4 mb-8">
            <a 
              href={deal.url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-center py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20"
            >
              <span>View Deal at {deal.store}</span>
              <ExternalLink className="w-5 h-5" />
            </a>
            <button 
              onClick={() => isComparing(deal.id) ? removeFromCompare(deal.id) : addToCompare(deal)}
              className={cn(
                "px-6 py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all border",
                isComparing(deal.id)
                  ? "bg-slate-900 border-slate-900 text-white"
                  : "bg-white border-slate-200 text-slate-900 hover:border-slate-900"
              )}
            >
              <ArrowRightLeft className="w-5 h-5" />
              <span>{isComparing(deal.id) ? "Comparing" : "Compare"}</span>
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="bg-slate-50 p-4 rounded-xl flex items-center gap-3">
              <Store className="w-5 h-5 text-slate-400" />
              <div>
                <p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Retailer</p>
                <p className="text-sm font-bold text-slate-900">{deal.store}</p>
              </div>
            </div>
            <div className="bg-slate-50 p-4 rounded-xl flex items-center gap-3">
              <Calendar className="w-5 h-5 text-slate-400" />
              <div>
                <p className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Updated</p>
                <p className="text-sm font-bold text-slate-900">
                  {deal.updatedAt?.toDate ? deal.updatedAt.toDate().toLocaleDateString() : 'Just now'}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-4 pt-8 border-t border-slate-100">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-widest">Key Specifications</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-3">
              {deal.specs && Object.entries(deal.specs).map(([key, val]) => (
                <div key={key} className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                  <span className="text-sm font-bold text-slate-700 capitalize">{key}:</span>
                  <span className="text-sm text-slate-500">{val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
