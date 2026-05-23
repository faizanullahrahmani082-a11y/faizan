import React from 'react';
import { useLanguage } from '../LanguageContext';
import { Card, CardContent } from './ui/card';
import { Check, Stethoscope, User, Pill, Wrench } from 'lucide-react';

const UserTypeSelector = ({ value, onChange }) => {
  const { t } = useLanguage();

  const userTypes = [
    { id: 'Doctor', label: t('doctor'), icon: Stethoscope },
    { id: 'Patient', label: t('patient'), icon: User },
    { id: 'Pharmacy', label: t('pharmacist'), icon: Pill },
    { id: 'Biomedical Engineer', label: t('biomedicalEngineer'), icon: Wrench },
  ];

  return (
    <div className="w-full">
      <label className="text-sm font-medium tracking-wide uppercase text-muted-foreground mb-3 block text-start">
        {t('selectUserType')}
      </label>
      <div className="grid grid-cols-2 gap-3">
        {userTypes.map((type) => {
          const Icon = type.icon;
          const isSelected = value === type.id;
          return (
            <Card
              key={type.id}
              onClick={() => onChange(type.id)}
              data-testid={`user-type-${type.id.toLowerCase().replace(' ', '-')}`}
              className={`cursor-pointer transition-all duration-200 hover:shadow-md ${
                isSelected
                  ? 'border-primary bg-teal-50 dark:bg-teal-900/20 border-2'
                  : 'border hover:border-primary/50'
              }`}
            >
              <CardContent className="p-4 flex flex-col items-center justify-center gap-2 relative">
                {isSelected && (
                  <div className="absolute top-2 end-2 bg-primary rounded-full p-1">
                    <Check className="w-3 h-3 text-primary-foreground" />
                  </div>
                )}
                <Icon className={`w-8 h-8 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                <span className={`text-sm font-medium text-center ${isSelected ? 'text-primary' : 'text-foreground'}`}>
                  {type.label}
                </span>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
};

export default UserTypeSelector;
