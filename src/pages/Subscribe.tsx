import { useState, type FormEvent } from 'react';
import { gamingDealsService } from '../lib/dealsService';
import { Bell, CheckCircle, Mail, MessageSquare } from 'lucide-react';
import { cn } from '../lib/utils';

export function Subscribe() {
  const [email, setEmail] = useState('');
  const [whatsapp, setWhatsapp] = useState('');
  const [categories, setCategories] = useState<string[]>(['laptop', 'cpu', 'gpu']);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    
    await gamingDealsService.subscribeForAlerts({
      email: email || undefined,
      whatsapp: whatsapp || undefined,
      categories
    });

    setSubmitted(true);
    setLoading(false);
  };

  if (submitted) {
    return (
      <div className="max-w-md mx-auto py-20 text-center animate-in fade-in zoom-in duration-500">
        <div className="w-20 h-20 bg-emerald-100 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-6">
          <CheckCircle className="w-10 h-10" />
        </div>
        <h2 className="text-3xl font-bold text-slate-900 mb-2">You're on the list!</h2>
        <p className="text-slate-500 mb-8">We'll alert you the moment a massive hardware discount drops in UAE.</p>
        <button 
          onClick={() => setSubmitted(false)}
          className="text-blue-600 font-bold hover:underline"
        >
          Subscribe another contact
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-20">
      <div className="text-center mb-16">
        <h1 className="text-4xl md:text-5xl font-extrabold text-slate-900 tracking-tight lg:text-6xl mb-4">
          Never miss a <span className="text-blue-600">Flash Sale.</span>
        </h1>
        <p className="text-lg text-slate-500 max-w-2xl mx-auto">
          Get instant alerts via Email or WhatsApp when premium hardware hits its lowest price in UAE history.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
        <div className="bg-slate-900 text-white p-8 md:p-10 rounded-3xl relative overflow-hidden">
          <Bell className="absolute -top-10 -right-10 w-40 h-40 text-white/5 rotate-12" />
          <h3 className="text-2xl font-bold mb-6 relative z-10">Why subscribe?</h3>
          <ul className="space-y-6 relative z-10">
            <li className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-white" />
              </div>
              <p className="text-slate-300 text-sm font-medium">Real-time alerts for price drops over 15% on high-end hardware.</p>
            </li>
            <li className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-white" />
              </div>
              <p className="text-slate-300 text-sm font-medium">Exclusive deals from local retailers like Amazon AE, Microless, and Gear-up.</p>
            </li>
            <li className="flex gap-4">
              <div className="flex-shrink-0 w-8 h-8 bg-slate-700 rounded-lg flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-white" />
              </div>
              <p className="text-slate-300 text-sm font-medium">No spam. Only hardware alerts you actually care about.</p>
            </li>
          </ul>
        </div>

        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 p-8 md:p-10 rounded-3xl shadow-xl shadow-slate-200/50">
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-bold text-slate-900 uppercase tracking-widest mb-2">Email Address</label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@email.com"
                  className="w-full bg-slate-50 border-none py-4 pl-12 pr-4 rounded-xl focus:ring-2 focus:ring-blue-600/20 outline-none placeholder:text-slate-400"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-900 uppercase tracking-widest mb-2">WhatsApp (Optional)</label>
              <div className="relative">
                <MessageSquare className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  type="tel"
                  value={whatsapp}
                  onChange={(e) => setWhatsapp(e.target.value)}
                  placeholder="+971 50..."
                  className="w-full bg-slate-50 border-none py-4 pl-12 pr-4 rounded-xl focus:ring-2 focus:ring-blue-600/20 outline-none placeholder:text-slate-400"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-bold text-slate-900 uppercase tracking-widest mb-4">Interested In</label>
              <div className="flex flex-wrap gap-3">
                {['laptop', 'cpu', 'gpu'].map(cat => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => {
                      setCategories(prev => 
                        prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
                      );
                    }}
                    className={cn(
                      "px-4 py-2 rounded-full text-xs font-bold uppercase transition-all border",
                      categories.includes(cat)
                        ? "bg-blue-600 border-blue-600 text-white"
                        : "bg-white border-slate-200 text-slate-600 hover:border-blue-600 hover:text-blue-600"
                    )}
                  >
                    {cat}s
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || (!email && !whatsapp)}
              className="w-full bg-slate-900 hover:bg-black text-white text-center py-4 rounded-xl font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Joining..." : "Enable My Alerts"}
            </button>
            <p className="text-[10px] text-slate-400 text-center font-medium">
              By subscribing, you agree to receive price monitoring alerts for UAE. Unsubscribe at any time.
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
