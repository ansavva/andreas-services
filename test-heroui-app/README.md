# {{PROJECT_TITLE}}

This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-heroui-app`](https://github.com/your-username/create-heroui-app).

## Features

- ⚡️ **Next.js 15** with App Router
- 🎨 **HeroUI** - Beautiful React components
- 🔷 **TypeScript** - Type safety out of the box
- 🎯 **Tailwind CSS** - Utility-first CSS framework
- ☁️ **Cloudflare** - Ready for deployment

## Getting Started

First, run the development server:

```bash
pnpm dev
# or
npm run dev
# or
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `src/app/page.tsx`. The page auto-updates as you edit the file.

## Learn More

To learn more about the technologies used in this project:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [HeroUI Documentation](https://heroui.com) - learn about HeroUI components.
- [Tailwind CSS Documentation](https://tailwindcss.com/docs) - learn about Tailwind CSS.
- [TypeScript Documentation](https://www.typescriptlang.org/docs) - learn about TypeScript.

## Deploy on Cloudflare

The easiest way to deploy your Next.js app is to use the Cloudflare integration:

```bash
pnpm deploy
```

This will build and deploy your app to Cloudflare Pages/Workers.

You can also deploy to other platforms like [Vercel](https://vercel.com/new) or [Netlify](https://www.netlify.com/).

## Project Structure

```
├── public/          # Static files
├── src/
│   └── app/         # App Router pages and layouts
│       ├── globals.css    # Global styles
│       ├── layout.tsx     # Root layout
│       ├── page.tsx       # Home page
│       └── providers.tsx  # HeroUI provider
├── next.config.ts   # Next.js configuration
├── tailwind.config.js     # Tailwind CSS configuration
└── tsconfig.json    # TypeScript configuration
```
