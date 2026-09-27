import { resolve } from 'node:path'
import config from '../../maatools.config.mts'

// Keep candidate validation on the same runtime as the frozen build dependencies.
// Update this pin together with deps/, install/maafw and the release manifest.
export default {
  ...config,
  maaVersion: '5.13.0',
  maaCache: resolve(import.meta.dirname, '../../.cache/maa-tools'),
}
