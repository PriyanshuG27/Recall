import axios from 'axios';

const client = axios.create({
  baseURL: '',
});

let unauthorizedHandler = null;
let toastHandler = null;

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function setToastHandler(handler) {
  toastHandler = handler;
}

// Translate status and server error payloads into human-readable user errors
function getErrorMessage(error) {
  if (!error.response) {
    return 'Connection lost — check your internet';
  }
  
  const { status } = error.response;
  switch (status) {
    case 400:
      return 'Invalid request details provided.';
    case 401:
      return 'Session expired — please log in again';
    case 403:
      return 'Access denied — you do not have permission';
    case 404:
      return 'Requested resource not found';
    case 429:
      return 'Too many requests — please wait';
    case 503:
      return 'Server unavailable — retrying in 30 s';
    default:
      return 'An unexpected server error occurred';
  }
}

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const { response, config } = error;
    
    // 1. Network Error (no response)
    if (!response) {
      if (toastHandler && navigator.onLine) {
        toastHandler('Connection lost — check your internet', 'error');
      }
      error.userMessage = 'Connection lost — check your internet';
      return Promise.reject(error);
    }

    const { status } = response;
    const url = config.url || '';

    // 2. 401 Unauthorized (exclude auth endpoints to prevent redirect loops)
    if (status === 401) {
      const isAuthEndpoint = url.startsWith('/auth/') || url.includes('/auth/me') || url.includes('/auth/logout');
      if (!isAuthEndpoint) {
        if (unauthorizedHandler) {
          unauthorizedHandler();
        }
      }
    } 
    // 3. 429 Too Many Requests
    else if (status === 429) {
      if (toastHandler) {
        toastHandler('Too many requests — please wait', 'warning');
      }
    } 
    // 4. 503 Service Unavailable
    else if (status === 503) {
      if (toastHandler) {
        toastHandler('Server unavailable — retrying in 30 s', 'error');
      }
    }

    error.userMessage = getErrorMessage(error);
    return Promise.reject(error);
  }
);

export default client;
