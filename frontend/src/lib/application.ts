const KEY = "mb_application_id";

export function getStoredApplicationId(): number | null {
  const v = localStorage.getItem(KEY);
  return v ? parseInt(v, 10) : null;
}
export function setStoredApplicationId(id: number) {
  localStorage.setItem(KEY, String(id));
}
export function clearStoredApplicationId() {
  localStorage.removeItem(KEY);
}