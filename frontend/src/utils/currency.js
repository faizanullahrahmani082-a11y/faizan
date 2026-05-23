export const CURRENCIES = [
  { code: 'USD', symbol: '$', name: 'US Dollar' },
  { code: 'AFN', symbol: '؋', name: 'Afghan Afghani (Af)' },
];

export const getCurrencySymbol = (code) =>
  CURRENCIES.find((c) => c.code === code)?.symbol ?? '$';

export const formatPrice = (amount, currency = 'USD') =>
  `${getCurrencySymbol(currency)}${Number(amount || 0).toFixed(2)}`;
