import { Link, useLocation } from 'react-router-dom';
import { Cpu, Laptop, HardDrive, Bell, Zap, LogIn, LogOut, User } from 'lucide-react';
import { cn } from '../lib/utils';
import { auth, signInWithGoogle, logout } from '../lib/firebase';
import { onAuthStateChanged, User as FirebaseUser } from 'firebase/auth';
import { useState, useEffect } from 'react';

export function Navbar() {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const activeType = searchParams.get('type');
  const [user, setUser] = useState<FirebaseUser | null>(null);

  useEffect(() => {
    return onAuthStateChanged(auth, (u) => setUser(u));
  }, []);

  const navItems = [
    { name: 'All Deals', path: '/', isActive: !activeType && location.pathname === '/' },
    { name: 'Gaming Laptops', path: '/?type=laptop', isActive: activeType === 'laptop' },
    { name: 'CPUs', path: '/?type=cpu', isActive: activeType === 'cpu' },
    { name: 'GPUs', path: '/?type=gpu', isActive: activeType === 'gpu' },
  ];

  return (
    <div className="flex flex-col">
      {/* Top Nav */}
      <nav className="bg-slate-900 text-white h-16 flex items-center">
        <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 flex justify-between items-center">
          <Link to="/" className="flex items-center gap-2 font-bold text-xl tracking-tighter">
            OASIS <span className="text-blue-600">DEALS</span>
          </Link>
          
          <div className="flex items-center gap-6">
            <div className="hidden sm:flex items-center gap-2 text-sm text-slate-300 font-medium">
              <svg width="20" height="15" viewBox="0 0 3 2" className="rounded-sm">
                <rect width="1" height="2" fill="#00732f" />
                <rect width="2" height="2" x="1" fill="#fff" />
                <rect width="3" height="0.5" fill="#ff0000" x="0" y="1.5" />
              </svg>
              UAE
            </div>

            {user ? (
              <div className="flex items-center gap-3">
                <div className="flex flex-col items-end">
                  <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider leading-none">Admin</span>
                  <span className="text-xs font-medium text-white">{user.displayName}</span>
                </div>
                <button onClick={() => logout()} className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400 hover:text-white">
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <button 
                onClick={() => signInWithGoogle()}
                className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors text-sm font-medium"
              >
                <LogIn className="w-4 h-4" />
                <span>Sign In</span>
              </button>
            )}

            <Link 
              to="/subscribe" 
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            >
              Get Price Alerts
            </Link>
          </div>
        </div>
      </nav>

      {/* Category Bar */}
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center gap-8 h-14">
          {navItems.map((item) => (
            <Link
              key={item.name}
              to={item.path}
              className={cn(
                "text-sm font-medium h-full flex items-center border-b-2 transition-all",
                item.isActive
                  ? "text-blue-600 border-blue-600"
                  : "text-slate-800 border-transparent hover:text-blue-600"
              )}
            >
              {item.name}
            </Link>
          ))}
          
          <div className="ml-auto relative hidden md:block">
            <input 
              type="text" 
              placeholder="Search deals..." 
              className="w-64 bg-slate-100 border-none rounded-full py-1.5 px-4 text-sm focus:ring-2 focus:ring-blue-600/30 outline-none"
            />
          </div>
        </div>
      </nav>
    </div>
  );
}
