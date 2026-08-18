/**
 * Company names for the symbols the app ships with.
 *
 * A row that reads "AAPL · Apple Inc." is the difference between a terminal
 * and a consumer app. There is no names endpoint, so this covers the seed
 * watchlist plus the large caps a user is most likely to type; anything else
 * simply renders without a subtitle rather than with a placeholder.
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

/** The one or two letters shown on an instrument chip. */
export const instrumentMonogram = (ticker: string): string => ticker.slice(0, 2);
