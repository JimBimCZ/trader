/**
 * Company names for the symbols the app ships with. There is no names
 * endpoint, so anything outside this map renders without a subtitle.
 */
const NAMES: Record<string, string> = {
  AAPL: "Apple",
  GOOGL: "Alphabet",
  MSFT: "Microsoft",
  AMZN: "Amazon",
  TSLA: "Tesla",
  NVDA: "NVIDIA",
  META: "Meta Platforms",
  JPM: "JPMorgan Chase",
  V: "Visa",
  NFLX: "Netflix",
  AMD: "Advanced Micro Devices",
  INTC: "Intel",
  PYPL: "PayPal",
  DIS: "Walt Disney",
  BA: "Boeing",
  KO: "Coca-Cola",
  PEP: "PepsiCo",
  WMT: "Walmart",
  XOM: "Exxon Mobil",
  CRM: "Salesforce",
  ORCL: "Oracle",
  ADBE: "Adobe",
  UBER: "Uber",
  SHOP: "Shopify",
  SQ: "Block",
  COIN: "Coinbase",
  MA: "Mastercard",
  BAC: "Bank of America",
  T: "AT&T",
  F: "Ford",
};

export const instrumentName = (ticker: string): string | null => NAMES[ticker] ?? null;

export const instrumentMonogram = (ticker: string): string => ticker.slice(0, 2);
