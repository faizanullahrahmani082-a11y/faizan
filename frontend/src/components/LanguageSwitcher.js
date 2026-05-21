import React from 'react';
import { useLanguage } from '../LanguageContext';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Globe } from 'lucide-react';

const LanguageSwitcher = () => {
  const { language, setLanguage } = useLanguage();

  const languages = [
    { code: 'en', name: 'English', nativeName: 'English' },
    { code: 'fa', name: 'Farsi', nativeName: 'فارسی' },
    { code: 'ps', name: 'Pashto', nativeName: 'پښتو' },
  ];

  return (
    <div className="flex items-center gap-2" data-testid="language-switcher">
      <Globe className="w-4 h-4 text-muted-foreground" />
      <Select value={language} onValueChange={setLanguage}>
        <SelectTrigger className="w-[140px]" data-testid="language-select-trigger">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {languages.map((lang) => (
            <SelectItem key={lang.code} value={lang.code} data-testid={`language-option-${lang.code}`}>
              {lang.nativeName}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};

export default LanguageSwitcher;
