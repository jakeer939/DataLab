import React, { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import AuthLayout from '../components/AuthLayout'
import { ErrorMessage } from '../components/Feedback'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../api/client'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user) {
    return <Navigate to="/" replace />
  }

  const handleChange = (event) => {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login({
        username: form.username.trim(),
        password: form.password,
      })
      const destination = location.state?.from || '/'
      navigate(destination, { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to sign in'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to continue to your workspace."
      footer={
        <>
          New to DataLab?{' '}
          <Link to="/register" className="font-semibold text-brand-600 hover:text-brand-700">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <ErrorMessage message={error} />
        <div>
          <label className="label" htmlFor="username">
            Username or email
          </label>
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            className="input"
            value={form.username}
            onChange={handleChange}
            required
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            className="input"
            value={form.password}
            onChange={handleChange}
            required
            placeholder="••••••••"
          />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          <LogIn className="h-4 w-4" />
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  )
}
