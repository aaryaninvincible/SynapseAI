import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";
import { getAnalytics, isSupported } from "firebase/analytics";

const firebaseConfig = {
  apiKey: "AIzaSyBgdh6CGUZbZpQdgny1WthcbLKXpp044Nk",
  authDomain: "webdev-68c40.firebaseapp.com",
  databaseURL: "https://webdev-68c40-default-rtdb.firebaseio.com",
  projectId: "webdev-68c40",
  storageBucket: "webdev-68c40.firebasestorage.app",
  messagingSenderId: "637071020410",
  appId: "1:637071020410:web:b925f7e17286bbd73686c3",
  measurementId: "G-H1QQ0GR9HB"
};

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);

isSupported().then((supported) => {
  if (supported) {
    getAnalytics(app);
  }
});
