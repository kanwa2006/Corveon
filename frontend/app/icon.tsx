import { ImageResponse } from 'next/og';

export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

export default function Icon(): ImageResponse {
  return new ImageResponse(
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0b60ea',
        borderRadius: 6,
        color: '#f8fafc',
        fontSize: 20,
        fontWeight: 700,
        fontFamily: 'sans-serif',
      }}
    >
      C
    </div>,
    size,
  );
}
