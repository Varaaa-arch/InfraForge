export interface ApiResponse<T> {
  success: boolean;
  data: T;
}

export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiErrorBody {
  detail?: string | ValidationErrorItem[];
  message?: string;
}
