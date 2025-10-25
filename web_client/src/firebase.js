
// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { initializeAuth, browserLocalPersistence, inMemoryPersistence } from "firebase/auth";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyA5_i6uqq3NWQ5AqIwZWsaPRn47DPLWAV8",
  authDomain: "sftt-3626f.firebaseapp.com",
  projectId: "sftt-3626f",
  storageBucket: "sftt-3626f.firebasestorage.app",
  messagingSenderId: "545144373555",
  appId: "1:545144373555:web:dea6ac0c75a038fe70be46",
  measurementId: "G-6525Q429R3"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Cloud Firestore and get a reference to the service
const db = getFirestore(app);

// Initialize Firebase Authentication and get a reference to the service
const isEmbedRoute = typeof window !== "undefined" && window.location.pathname.startsWith("/embed/");
const auth = initializeAuth(app, {
  persistence: isEmbedRoute ? inMemoryPersistence : [browserLocalPersistence],
});

export { db, auth };
