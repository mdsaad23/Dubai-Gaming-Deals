import { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { gamingDealsService } from '../lib/dealsService';
import { Deal, ProductType } from '../types';
import { Laptop, Cpu, HardDrive, Package, ArrowRightLeft } from 'lucide-react';
import { cn } from '../lib/utils';
import { useComparison } from '../lib/ComparisonContext';
import { auth, signInWithGoogle } from '../lib/firebase';
import { onAuthStateChanged, User as FirebaseUser } from 'firebase/auth';

export function Home() {
  const [searchParams] = useSearchParams();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<FirebaseUser | null>(null);
  const activeType = searchParams.get('type') as ProductType | null;

  useEffect(() => {
    onAuthStateChanged(auth, u => setUser(u));
  }, []);

  useEffect(() => {
    setLoading(true);
    const unsubscribe = gamingDealsService.subscribeToDeals((data) => {
      setDeals(data);
      setLoading(false);
    }, activeType || undefined);

    return () => unsubscribe();
  }, [activeType]);

  const filters = [
    { title: 'Manufacturer', options: ['ASUS ROG', 'Lenovo Legion', 'Razer', 'MSI', 'Gigabyte', 'AMD', 'Intel', 'NVIDIA'] },
    { title: 'Price Range (AED)', type: 'range' }
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] min-h-[calc(100vh-120px)]">
      {/* Sidebar */}
      <aside className="border-r border-slate-200 bg-white p-6 hidden lg:block overflow-y-auto">
        {filters.map((filter) => (
          <div key={filter.title} className="mb-8">
            <h3 className="text-[12px] uppercase tracking-widest text-slate-900 font-bold mb-4">{filter.title}</h3>
            {filter.type === 'range' ? (
              <div className="flex flex-col gap-2 mt-2">
                <input type="range" className="w-full accent-blue-600" min="0" max="20000" />
                <div className="flex justify-between text-[11px] text-slate-500 font-medium">
                  <span>0 AED</span>
                  <span>20,000+</span>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {filter.options?.map((opt) => (
                  <label key={opt} className="flex items-center gap-3 text-sm text-slate-700 cursor-pointer hover:text-blue-600 transition-colors">
                    <input type="checkbox" className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-600/20" />
                    {opt}
                  </label>
                ))}
              </div>
            )}
          </div>
        ))}
      </aside>

      {/* Main Content */}
      <section className="p-6 md:p-8">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-slate-900">
            Current {activeType ? activeType.toUpperCase() + 's' : 'Gaming Hardware'} Deals
          </h1>
          <p className="text-slate-500 text-sm mt-1">Found {deals.length} active offers for UAE</p>
        </header>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="bg-white border border-slate-200 rounded-xl h-64 animate-pulse" />
            ))}
          </div>
        ) : deals.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-6">
            {deals.map((deal) => (
              <DealCard key={deal.id} deal={deal} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 bg-white border border-slate-200 rounded-2xl">
            <Package className="w-12 h-12 text-slate-200 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-slate-900">No deals found</h3>
            <p className="text-slate-500 text-sm mb-6">Check back later or change your filters.</p>
            <button 
              onClick={async () => {
                setLoading(true);
                const { seedDatabase } = await import('../../seed');
                await seedDatabase();
                setLoading(false);
              }}
              disabled={loading}
              className="px-6 py-2 bg-slate-900 text-white rounded-full text-sm font-bold hover:bg-black transition-all disabled:opacity-50"
            >
              {loading ? "Seeding..." : "Seed Sample Deals"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

interface DealCardProps {
  deal: Deal;
}

function DealCard({ deal }: DealCardProps) {
  const Icon = deal.productType === 'laptop' ? Laptop : deal.productType === 'cpu' ? Cpu : HardDrive;
  const { addToCompare, isComparing, removeFromCompare } = useComparison();
  const comparing = isComparing(deal.id);
  
  return (
    <div className="group bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 relative">
      <Link 
        to={`/deal/${deal.id}`}
        className="block"
      >
        <div className="h-44 bg-slate-50 flex items-center justify-center relative inner-shadow">
          {deal.discountPercentage > 0 && (
            <span className="absolute top-3 left-3 bg-emerald-500 text-white text-[10px] font-bold px-2 py-1 rounded z-10">
              {Math.round(deal.discountPercentage)}% OFF
            </span>
          )}
          {deal.imageUrl ? (
            <img src={deal.imageUrl} alt={deal.productName} className="h-32 w-auto object-contain p-4 group-hover:scale-105 transition-transform duration-500" referrerPolicy="no-referrer" />
          ) : (
            <Icon className="w-12 h-12 text-slate-300 stroke-1" />
          )}
        </div>
      </Link>

      <button 
        onClick={(e) => {
          e.preventDefault();
          comparing ? removeFromCompare(deal.id) : addToCompare(deal);
        }}
        className={cn(
          "absolute top-3 right-3 p-2 rounded-lg backdrop-blur-md transition-all z-20",
          comparing 
            ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" 
            : "bg-white/80 text-slate-400 hover:text-blue-600 border border-slate-200"
        )}
        title={comparing ? "Remove from comparison" : "Add to comparison"}
      >
        <ArrowRightLeft className="w-4 h-4" />
      </button>

      <div className="p-4">
        <Link to={`/deal/${deal.id}`}>
          <h4 className="text-sm font-semibold text-slate-900 line-clamp-2 min-h-[40px] leading-tight mb-3 hover:text-blue-600">
            {deal.productName}
          </h4>
        </Link>
        <div className="flex items-baseline gap-2 mb-4">
          <span className="text-lg font-bold text-slate-900">AED {deal.price.toLocaleString()}</span>
          {deal.previousPrice && deal.previousPrice > deal.price ? (
            <span className="text-[10px] bg-red-100 text-red-600 px-1.5 py-0.5 rounded font-bold uppercase">
              Drop
            </span>
          ) : deal.originalPrice > deal.price && (
            <span className="text-xs text-slate-400 line-through font-medium">AED {deal.originalPrice.toLocaleString()}</span>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {deal.specs && Object.entries(deal.specs).slice(0, 2).map(([key, val]) => (
            <span key={key} className="bg-slate-100 text-[10px] text-slate-800 font-semibold px-2 py-0.5 rounded capitalize">
              {val}
            </span>
          ))}
          <span className="bg-blue-50 text-[10px] text-blue-700 font-bold px-2 py-0.5 rounded uppercase ml-auto">
            {deal.store}
          </span>
        </div>
      </div>
    </div>
  );
}
