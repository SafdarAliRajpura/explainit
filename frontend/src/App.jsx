import Hero from './components/Hero';
import { LanguageProvider } from './context/LanguageContext';

function App() {
  return (
    <LanguageProvider>
      <Hero />
    </LanguageProvider>
  );
}

export default App;
