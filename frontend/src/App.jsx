import React from 'react'
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Datasets from './pages/Datasets'
import DatasetUpload from './pages/DatasetUpload'
import DatasetDetails from './pages/DatasetDetails'
import Analysis from './pages/Analysis'
import Cleaning from './pages/Cleaning'
import Experiments from './pages/Experiments'
import ModelLeaderboard from './pages/ModelLeaderboard'
import ModelDetails from './pages/ModelDetails'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="datasets/upload" element={<DatasetUpload />} />
        <Route path="datasets/:datasetId" element={<DatasetDetails />} />
        <Route path="datasets/:datasetId/analysis" element={<Analysis />} />
        <Route path="datasets/:datasetId/cleaning" element={<Cleaning />} />
        <Route path="experiments" element={<Experiments />} />
        <Route path="experiments/:experimentId" element={<Experiments />} />
        <Route path="models" element={<ModelLeaderboard />} />
        <Route path="models/:modelId" element={<ModelDetails />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
