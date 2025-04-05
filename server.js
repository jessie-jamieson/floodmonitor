const express = require('express');
const axios = require('axios');
const cors = require('cors');
const path = require('path');

const app = express();
const port = 3000;

// Enable CORS for all routes
app.use(cors());

// Serve static files from the public directory
app.use(express.static(path.join(__dirname, 'public')));

// Proxy endpoint for USGS API
app.get('/api/usgs', async (req, res) => {
  try {
    const bbox = req.query.bbox;
    const parameterCd = req.query.parameterCd || '00065,00060';
    
    console.log(`Proxying request to USGS with bbox: ${bbox}`);
    
    const response = await axios.get(`https://waterservices.usgs.gov/nwis/iv/`, {
      params: {
        format: 'json',
        bBox: bbox,
        parameterCd: parameterCd,
        siteStatus: 'active'
      },
      timeout: 10000 // 10 second timeout
    });
    
    console.log(`USGS response received with ${response.data.value?.timeSeries?.length || 0} time series`);
    
    res.json(response.data);
  } catch (error) {
    console.error('Error fetching USGS data:', error.message);
    res.status(500).json({ 
      error: 'Error fetching USGS data', 
      message: error.message 
    });
  }
});

// Start the server
app.listen(port, () => {
  console.log(`USGS proxy server running at http://localhost:${port}`);
});