import { createContext, useContext } from 'react';

export const AuthContext = createContext({
  authReady: false,
});

export const useAuthContext = () => useContext(AuthContext);
