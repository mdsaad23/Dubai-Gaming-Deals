import { db } from './src/lib/firebase';
import { collection, addDoc, serverTimestamp } from 'firebase/firestore';

const sampleDeals = [
  {
    productName: "Razer Blade 16 (2024) - QHD+ 240Hz - RTX 4080",
    productType: "laptop",
    price: 12499,
    originalPrice: 14700,
    previousPrice: 13500,
    discountPercentage: 15,
    store: "Amazon AE",
    url: "https://amazon.ae",
    country: "UAE",
    specs: { gpu: "RTX 4080", cpu: "i9-14900HX", ram: "32GB" },
    imageUrl: "https://images.unsplash.com/photo-1544161515-4ae6ce6ca8b8?q=80&w=2670&auto=format&fit=crop"
  },
  {
    productName: "AMD Ryzen 7 7800X3D Processor",
    productType: "cpu",
    price: 1450,
    originalPrice: 1850,
    previousPrice: 1620,
    discountPercentage: 21,
    store: "Microless",
    url: "https://microless.com",
    country: "UAE",
    specs: { cores: "8", boost: "5.0GHz", socket: "AM5" },
    imageUrl: "https://images.unsplash.com/photo-1591488320449-011701bb6704?q=80&w=2670&auto=format&fit=crop"
  },
  {
    productName: "ASUS ROG Strix GeForce RTX 4090 OC Edition",
    productType: "gpu",
    price: 7899,
    originalPrice: 8500,
    previousPrice: 8200,
    discountPercentage: 7,
    store: "Gear-up",
    url: "https://gear-up.me",
    country: "UAE",
    specs: { vram: "24GB", series: "RTX 4090", clock: "2.6GHz" },
    imageUrl: "https://images.unsplash.com/photo-1591443125582-143f9cd1332f?q=80&w=2640&auto=format&fit=crop"
  }
];

export async function seedDatabase() {
  console.log("Seeding database...");
  for (const deal of sampleDeals) {
    try {
      await addDoc(collection(db, 'deals'), {
        ...deal,
        productId: 'sample-' + Math.random().toString(36).substr(2, 9),
        updatedAt: serverTimestamp()
      });
      console.log(`Added deal: ${deal.productName}`);
    } catch (e) {
      console.error("Error adding deal: ", e);
    }
  }
  console.log("Seeding complete!");
}
