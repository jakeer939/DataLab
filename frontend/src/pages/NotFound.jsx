import React from 'react'
import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import PageHeader from '../components/PageHeader'

export default function NotFound() {
  return (
    <div>
      <PageHeader
        eyebrow="404"
        title="Page not found"
        description="The page you are looking for does not exist or may have been moved."
      />
      <div className="card flex flex-col items-center justify-center px-6 py-16 text-center">
        <Compass className="mb-4 h-12 w-12 text-slate-300" />
        <p className="max-w-md text-sm text-slate-500">
          Check the address, or head back to your dashboard to continue working with your
          datasets and models.
        </p>
        <Link to="/" className="btn-primary mt-6">
          Back to dashboard
        </Link>
      </div>
    </div>
  )
}
