/**
 * Icons.jsx — outline icons (24px grid, currentColor) used across the app,
 * drawn in the same style as the tab icons so every page reads as one set.
 */
function Icon({ size = 18, children, className, strokeWidth = 1.8, label }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : 'true'}
      focusable="false"
    >
      {children}
    </svg>
  )
}

const make = paths => props => <Icon {...props}>{paths}</Icon>

export const CardIcon = make(<>
  <rect x="2.5" y="5" width="19" height="14" rx="2.5" /><path d="M2.5 10h19" /><path d="M6.5 15h4" />
</>)
export const ChartIcon = make(<>
  <path d="M4 20V10" /><path d="M10 20V4" /><path d="M16 20v-7" /><path d="M22 20H2" />
</>)
export const SwapIcon = make(<>
  <path d="M7 4 3 8l4 4" /><path d="M3 8h14" /><path d="m17 20 4-4-4-4" /><path d="M21 16H7" />
</>)
export const BulbIcon = make(<>
  <path d="M9 18h6" /><path d="M10 21h4" />
  <path d="M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3Z" />
</>)
export const BoltIcon = make(<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />)
export const CheckIcon = make(<path d="m5 12.5 4.5 4.5L19 7.5" />)
export const CheckCircleIcon = make(<>
  <circle cx="12" cy="12" r="9" /><path d="m8 12.5 2.8 2.8L16.5 9.5" />
</>)
export const XIcon = make(<><path d="M6 6l12 12" /><path d="M18 6 6 18" /></>)
export const InfoIcon = make(<>
  <circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 7.5h.01" />
</>)
export const AlertIcon = make(<>
  <path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
  <path d="M12 9v4" /><path d="M12 17h.01" />
</>)
export const FileIcon = make(<>
  <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" />
  <path d="M9 13h6" /><path d="M9 17h4" />
</>)
export const UploadIcon = make(<>
  <path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
</>)
export const LockIcon = make(<>
  <rect x="4.5" y="10.5" width="15" height="10" rx="2" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
</>)
export const EyeIcon = make(<>
  <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />
</>)
export const EyeOffIcon = make(<>
  <path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-2.6 3.5" />
  <path d="M6.6 6.6C3.7 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6" />
  <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /><path d="m3 3 18 18" />
</>)
export const SearchIcon = make(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>)
export const CoinsIcon = make(<>
  <circle cx="9" cy="9" r="6" /><path d="M15.5 8.6A6 6 0 1 1 9.4 15.4" /><path d="M9 6.5v5" /><path d="M7 9h4" />
</>)
export const ArrowLeftIcon = make(<><path d="M19 12H5" /><path d="m11 18-6-6 6-6" /></>)
export const ArrowRightIcon = make(<><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>)
export const TargetIcon = make(<>
  <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" />
</>)
export const TrendUpIcon = make(<><path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" /></>)
export const TrendDownIcon = make(<><path d="m3 7 6 6 4-4 8 8" /><path d="M15 17h6v-6" /></>)
export const RepeatIcon = make(<>
  <path d="m17 2 4 4-4 4" /><path d="M3 11v-1a4 4 0 0 1 4-4h14" /><path d="m7 22-4-4 4-4" /><path d="M21 13v1a4 4 0 0 1-4 4H3" />
</>)
export const SparkIcon = make(<>
  <path d="M12 3v4" /><path d="M12 17v4" /><path d="M3 12h4" /><path d="M17 12h4" />
  <path d="m6 6 2.5 2.5" /><path d="m15.5 15.5 2.5 2.5" /><path d="m6 18 2.5-2.5" /><path d="m15.5 8.5 2.5-2.5" />
</>)
