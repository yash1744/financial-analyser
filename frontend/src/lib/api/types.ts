/** TypeScript mirrors of the backend's Pydantic schemas (app/schemas/). */

// --- auth ---

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// --- accounts ---

export interface Account {
  id: string;
  plaid_account_id: string;
  name: string;
  account_type: string;
  account_subtype: string | null;
  current_balance: string | null;
  available_balance: string | null;
  currency: string;
}

export interface ItemAccountsSyncSummary {
  item_id: string;
  plaid_item_id: string;
  institution_name: string | null;
  created: number;
  updated: number;
  skipped: number;
  accounts: Account[];
}

export interface AccountsSyncResponse {
  items: ItemAccountsSyncSummary[];
}

// --- transactions ---

export type TransactionType = "debit" | "credit";

export type TransactionClassification =
  | "income"
  | "expense"
  | "transfer"
  | "fee"
  | "refund"
  | "unknown";

export interface Transaction {
  id: string;
  account_id: string;
  plaid_transaction_id: string;
  transaction_date: string;
  merchant_name: string | null;
  amount: string;
  currency: string;
  category_id: string | null;
  transaction_type: TransactionType;
  classification: TransactionClassification;
  pending: boolean;
  created_at: string;
}

export type TransactionSortBy = "transaction_date" | "amount" | "merchant_name";
export type SortDir = "asc" | "desc";

// --- receipts ---

export interface ReceiptImage {
  id: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface Receipt {
  id: string;
  transaction_id: string;
  merchant_name: string | null;
  receipt_date: string | null;
  notes: string | null;
  tax_amount: string | null;
  tip_amount: string | null;
  comments: string | null;
  images: ReceiptImage[];
  created_at: string;
  updated_at: string;
}

export interface ReceiptDetailsUpdate {
  merchant_name?: string | null;
  receipt_date?: string | null;
  notes?: string | null;
  tax_amount?: string | null;
  tip_amount?: string | null;
  comments?: string | null;
}

export interface TransactionListParams {
  account_id?: string;
  category_id?: string;
  classification?: TransactionClassification;
  start_date?: string;
  end_date?: string;
  min_amount?: string;
  max_amount?: string;
  sort_by?: TransactionSortBy;
  sort_dir?: SortDir;
  page?: number;
  page_size?: number;
}

export interface PaginatedTransactions {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ItemTransactionsSyncSummary {
  item_id: string;
  plaid_item_id: string;
  institution_name: string | null;
  added: number;
  modified: number;
  removed: number;
  skipped: number;
  next_cursor: string;
  last_synced_at: string;
}

export interface TransactionsSyncResponse {
  items: ItemTransactionsSyncSummary[];
}

// --- categories ---

export interface Category {
  id: string;
  name: string;
  parent_category_id: string | null;
  created_at: string;
}

// --- plaid ---

export type PlaidItemStatus =
  | "active"
  | "login_required"
  | "error"
  | "disconnected";

export interface LinkTokenResponse {
  link_token: string;
  expiration: string;
}

export interface PlaidItem {
  id: string;
  plaid_item_id: string;
  institution_id: string | null;
  institution_name: string | null;
  status: PlaidItemStatus;
  created_at: string;
}

// --- analytics ---

export interface MonthlySpendingPoint {
  month: string; // "YYYY-MM"
  spending: string;
  income: string;
  net: string;
  transaction_count: number;
}

export interface MonthlySpendingResponse {
  months: MonthlySpendingPoint[];
}

export interface CategoryBreakdownItem {
  category_id: string | null;
  category_name: string;
  total: string;
  transaction_count: number;
  share_pct: number;
}

export interface CategoryBreakdownResponse {
  total_spending: string;
  categories: CategoryBreakdownItem[];
}

export interface TopMerchantItem {
  merchant_name: string;
  total: string;
  transaction_count: number;
}

export interface TopMerchantsResponse {
  merchants: TopMerchantItem[];
}

export interface MonthOverMonthPoint {
  month: string; // "YYYY-MM"
  spending: string;
  change: string | null;
  change_pct: number | null;
}

export interface MonthOverMonthResponse {
  months: MonthOverMonthPoint[];
}
