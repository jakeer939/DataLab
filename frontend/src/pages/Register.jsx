import React, { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { UserPlus } from 'lucide-react'
import AuthLayout from '../components/AuthLayout'
import { ErrorMessage } from '../components/Feedback'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../api/client'

const INITIAL_FORM = {
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
}

export default function Register() {
  const { user, register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState(INITIAL_FORM)
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

    if (form.username.trim().length < 3) {
      setError('Username must be at least 3 characters long')
      return
    }
    if (form.password.length < 6) {
      setError('Password must be at least 6 characters long')
      return
    }
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setSubmitting(true)
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to create your account'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start exploring, cleaning and modelling your data."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-brand-600 hover:text-brand-700">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <ErrorMessage message={error} />
        <div>
          <label className="label" htmlFor="username">
            Username
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
            minLength={3}
            placeholder="jane_doe"
          />
        </div>
        <div>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            className="input"
            value={form.email}
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
            autoComplete="new-password"
            className="input"
            value={form.password}
            onChange={handleChange}
            required
            minLength={6}
            placeholder="At least 6 characters"
          />
        </div>
        <div>
          <label className="label" htmlFor="confirmPassword">
            Confirm password
          </label>
          <input
            id="confirmPassword"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            className="input"
            value={form.confirmPassword}
            onChange={handleChange}
            required
            placeholder="Repeat your password"
          />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={submitting}>
          <UserPlus className="h-4 w-4" />
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthLayout>
  )
}
