import { 
  collection, 
  getDocs, 
  getDoc, 
  doc, 
  query, 
  where, 
  orderBy, 
  addDoc, 
  serverTimestamp,
  onSnapshot,
  Timestamp
} from 'firebase/firestore';
import { db, auth } from './firebase';
import { Product, Deal, AlertSubscription, ProductType } from '../types';

export enum OperationType {
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  LIST = 'list',
  GET = 'get',
  WRITE = 'write',
}

interface FirestoreErrorInfo {
  error: string;
  operationType: OperationType;
  path: string | null;
  authInfo: {
    userId?: string | null;
    email?: string | null;
    emailVerified?: boolean | null;
    isAnonymous?: boolean | null;
    tenantId?: string | null;
  }
}

function handleFirestoreError(error: unknown, operationType: OperationType, path: string | null) {
  const errInfo: FirestoreErrorInfo = {
    error: error instanceof Error ? error.message : String(error),
    authInfo: {
      userId: auth.currentUser?.uid,
      email: auth.currentUser?.email,
      emailVerified: auth.currentUser?.emailVerified,
      isAnonymous: auth.currentUser?.isAnonymous,
      tenantId: auth.currentUser?.tenantId,
    },
    operationType,
    path
  }
  console.error('Firestore Error: ', JSON.stringify(errInfo));
  throw new Error(JSON.stringify(errInfo));
}

export const gamingDealsService = {
  async getDeals(type?: ProductType): Promise<Deal[]> {
    const dealsPath = 'deals';
    try {
      let q = query(collection(db, dealsPath), orderBy('updatedAt', 'desc'));
      if (type) {
        q = query(q, where('productType', '==', type));
      }
      const snapshot = await getDocs(q);
      return snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Deal));
    } catch (error) {
      handleFirestoreError(error, OperationType.LIST, dealsPath);
      return [];
    }
  },

  async getDeal(id: string): Promise<Deal | null> {
    const path = `deals/${id}`;
    try {
      const docSnap = await getDoc(doc(db, 'deals', id));
      if (docSnap.exists()) {
        return { id: docSnap.id, ...docSnap.data() } as Deal;
      }
      return null;
    } catch (error) {
      handleFirestoreError(error, OperationType.GET, path);
      return null;
    }
  },

  async subscribeForAlerts(subscription: Partial<AlertSubscription>): Promise<string> {
    const path = 'subscriptions';
    try {
      const docRef = await addDoc(collection(db, path), {
        ...subscription,
        createdAt: serverTimestamp(),
      });
      return docRef.id;
    } catch (error) {
      handleFirestoreError(error, OperationType.CREATE, path);
      return '';
    }
  },

  // Helper for real-time deals (Home page)
  subscribeToDeals(callback: (deals: Deal[]) => void, type?: ProductType) {
    const dealsPath = 'deals';
    let q = query(collection(db, dealsPath), orderBy('updatedAt', 'desc'));
    if (type) {
      q = query(q, where('productType', '==', type));
    }
    
    return onSnapshot(q, (snapshot) => {
      const deals = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as Deal));
      callback(deals);
    }, (error) => {
      handleFirestoreError(error, OperationType.LIST, dealsPath);
    });
  }
};
