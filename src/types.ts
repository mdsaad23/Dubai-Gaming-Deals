export type ProductType = 'laptop' | 'cpu' | 'gpu';

export interface Product {
  id: string;
  name: string;
  type: ProductType;
  brand: string;
  specs: Record<string, any>;
  imageUrl?: string;
  updatedAt?: any;
}

export interface Deal {
  id: string;
  productId: string;
  productName: string;
  productType: ProductType;
  price: number;
  originalPrice: number;
  previousPrice?: number;
  currency: string;
  discountPercentage: number;
  store: string;
  url: string;
  country: string;
  updatedAt: any;
  specs: Record<string, any>;
  imageUrl?: string;
}

export interface AlertSubscription {
  id?: string;
  email?: string;
  whatsapp?: string;
  categories: string[];
  createdAt: any;
}
