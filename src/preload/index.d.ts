import type { StudioAPI } from '../shared/api'

declare global {
  interface Window {
    studio: StudioAPI
  }
}

export {}
